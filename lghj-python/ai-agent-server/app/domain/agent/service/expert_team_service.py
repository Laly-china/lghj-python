"""专家团（Expert Team）成员定义与权重配置服务。

设计说明（与用户需求对齐）：
- 专家团成员【角色固定、人数固定】：沿用投顾装配 YAML 中的 6 个专家 Agent，
  顺序与职责严格对齐 投顾装配-investment-advisor-supervisor.yml 的 sub-agents。
- 用户【只能调整各成员权重】：每个成员权重 0~100 的整数，全部成员权重之和须为 100。
  权重表达"本次投资计划中各专家的意见占比"。
- 权重【按用户独立保存】：userId -> {role_key: weight}，进程内存 Map（线程安全），
  与 ChatService 的 userSessions 缓存同一风格；默认权重为均分（6 人 -> 16/17/17/17/17/16）。
- 权重【在输出层加权汇总】：权重不仅影响 Supervisor 的调度倾向，还会在最终回复中
  要求 Supervisor 显式给出"按权重加权后的结论"，并标注各专家意见占比。

对应原系统：原 Java 无此功能（本模块为新增扩展，不修改原 6 专家的 instruction 文本，
避免破坏"instruction 严格照抄原文"的复现约束）。
"""

from __future__ import annotations

import logging
from threading import Lock

logger = logging.getLogger(__name__)


class ExpertTeamError(Exception):
    """专家团配置非法（权重越界 / 成员不存在 / 合计不为 100 等）。"""


#: 专家团固定成员（顺序、名称、职责与装配 YAML 的 sub-agents 严格对齐）
EXPERT_ROLES: list[dict] = [
    {
        "key": "MarketAnalysisAgent",
        "name": "市场分析师",
        "desc": "分析宏观环境、行业景气度、公司基本面和公开事件影响",
        "outputKey": "market_analysis",
    },
    {
        "key": "QuantTechnicalAgent",
        "name": "量化技术分析师",
        "desc": "分析价格、成交量、趋势、波动和技术风险",
        "outputKey": "quant_technical_analysis",
    },
    {
        "key": "PersonalTradeProfileAgent",
        "name": "个人交易行为分析师",
        "desc": "查询并分析当前用户的模拟交易画像，提供个性化依据",
        "outputKey": "personal_trade_profile",
    },
    {
        "key": "RiskAssessmentAgent",
        "name": "风险控制顾问",
        "desc": "识别投资风险、仓位风险、流动性风险和情景压力",
        "outputKey": "risk_assessment",
    },
    {
        "key": "PortfolioAdviceAgent",
        "name": "组合顾问",
        "desc": "给出组合配置、观察清单和行动建议",
        "outputKey": "portfolio_advice",
    },
    {
        "key": "ComplianceDisclosureAgent",
        "name": "合规审查员",
        "desc": "输出合规提示和免责声明",
        "outputKey": "compliance_disclosure",
    },
]

_ROLE_KEYS: set[str] = {r["key"] for r in EXPERT_ROLES}

#: 合规审查员兜底最低权重（合规相关意见不得被完全关闭，否则违反投顾合规要求）
_COMPLIANCE_MIN_WEIGHT = 5


def _default_weights() -> dict[str, int]:
    """默认均分权重：6 人，前 4 人 17、后 2 人 16（合计 100）。"""
    n = len(EXPERT_ROLES)
    base = 100 // n
    rem = 100 - base * n
    return {
        r["key"]: base + (1 if i < rem else 0)
        for i, r in enumerate(EXPERT_ROLES)
    }


class ExpertTeamService:
    """专家团权重配置服务（按 userId 独立保存，内存 Map + 线程锁）。"""

    def __init__(self) -> None:
        #: userId -> {role_key: weight}
        self._user_weights: dict[str, dict[str, int]] = {}
        self._lock = Lock()

    # ---------------- 查询 ----------------

    def query_config(self, user_id: str) -> dict:
        """返回该用户的专家团配置（成员固定 + 当前权重 + 是否自定义）。"""
        uid = str(user_id or "").strip()
        with self._lock:
            weights = dict(self._user_weights.get(uid) or {})
        is_custom = bool(weights)
        if not weights:
            weights = _default_weights()
        return {
            "userId": uid,
            "memberCount": len(EXPERT_ROLES),
            "editable": True,          # 仅权重可改
            "isCustom": is_custom,
            "totalWeight": sum(weights.values()),
            "members": [
                {**role, "weight": int(weights.get(role["key"], 0))}
                for role in EXPERT_ROLES
            ],
        }

    def get_weights(self, user_id: str) -> dict[str, int]:
        """取用户权重（未配置则返回默认均分）。"""
        uid = str(user_id or "").strip()
        with self._lock:
            configured = self._user_weights.get(uid)
            if configured:
                return dict(configured)
        return _default_weights()

    # ---------------- 更新 ----------------

    def update_weights(self, user_id: str, weights: dict) -> dict:
        """更新用户权重；返回更新后的完整配置。

        校验：
          1) 成员 key 必须全部来自固定角色库且不重不漏；
          2) 每个权重为 0~100 整数；
          3) 权重合计必须为 100；
          4) 合规审查员权重不得低于 _COMPLIANCE_MIN_WEIGHT。
        """
        uid = str(user_id or "").strip()
        if not uid:
            raise ExpertTeamError("userId 不能为空")
        if not isinstance(weights, dict) or not weights:
            raise ExpertTeamError("weights 必须为非空对象")

        provided = set(weights.keys())
        if provided != _ROLE_KEYS:
            missing = _ROLE_KEYS - provided
            extra = provided - _ROLE_KEYS
            detail = []
            if missing:
                detail.append(f"缺少成员: {sorted(missing)}")
            if extra:
                detail.append(f"未知成员: {sorted(extra)}")
            raise ExpertTeamError("成员组成固定不可变更（" + "；".join(detail) + "）")

        normalized: dict[str, int] = {}
        for key, raw in weights.items():
            try:
                val = int(raw)
            except (TypeError, ValueError):
                raise ExpertTeamError(f"成员 {key} 权重必须为整数") from None
            if val < 0 or val > 100:
                raise ExpertTeamError(f"成员 {key} 权重须在 0~100 之间")
            normalized[key] = val

        total = sum(normalized.values())
        if total != 100:
            raise ExpertTeamError(f"权重合计必须为 100（当前 {total}）")

        if normalized.get("ComplianceDisclosureAgent", 0) < _COMPLIANCE_MIN_WEIGHT:
            raise ExpertTeamError(
                f"合规审查员权重不得低于 {_COMPLIANCE_MIN_WEIGHT}（合规要求）"
            )

        with self._lock:
            self._user_weights[uid] = normalized
        logger.info("专家团权重已更新 userId=%s weights=%s", uid, normalized)
        return self.query_config(uid)

    def reset(self, user_id: str) -> dict:
        """重置为默认均分权重。"""
        uid = str(user_id or "").strip()
        with self._lock:
            self._user_weights.pop(uid, None)
        return self.query_config(uid)

    # ---------------- 上下文渲染（供 ChatService 注入） ----------------

    def render_weight_context(self, user_id: str) -> str:
        """把用户权重渲染为一段可注入模型上下文的中文说明。

        仅在用户做过自定义（非默认均分）时返回内容，避免污染默认链路。
        """
        uid = str(user_id or "").strip()
        with self._lock:
            configured = self._user_weights.get(uid)
        if not configured:
            return ""

        rows = []
        for role in EXPERT_ROLES:
            w = configured.get(role["key"], 0)
            if w > 0:
                rows.append(f"- {role['name']}（{role['key']}）：权重 {w}%")
        detail = "\n".join(rows)
        return (
            "\n【用户自定义专家团权重（用户已按个人预期调整，请在输出层加权汇总时遵循）】\n"
            f"{detail}\n"
            "要求：最终投资计划必须体现上述权重差异——把权重高的专家结论作为主线依据，"
            "权重低的专家结论作为补充或提示；并在回复的「主要依据」部分标注各专家意见的权重占比。"
            "注意：合规审查员的合规提示无论权重高低都必须完整保留。"
        )
