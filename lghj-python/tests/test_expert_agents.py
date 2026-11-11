"""立项扩展垂直 Agent（舆情/事件/资金流向）逐个补齐的契约自测。

按轮次追加：每补一个专家，本文件追加对应断言；通用一致性用例（人数联动/权重合计）
设计成与专家数量无关，三轮全过。
"""

from __future__ import annotations

import httpx
import pytest

from conftest import AGENT, INTERNAL_TOKEN, MAIN, assert_response_ok

#: 原生 6 专家 + 各轮补齐的立项扩展专家（与 yml sub-agents / EXPERT_ROLES 对齐）
ORIGINAL_EXPERTS = {
    "MarketAnalysisAgent", "QuantTechnicalAgent", "PersonalTradeProfileAgent",
    "RiskAssessmentAgent", "PortfolioAdviceAgent", "ComplianceDisclosureAgent",
}
#: 已补齐的立项扩展专家（逐轮追加：R1 舆情 → R2 事件 → R3 资金流向）
EXTENDED_EXPERTS = {
    "SentimentAnalysisAgent",
    "EventAnalysisAgent",
}


def _team(client: httpx.Client) -> dict:
    agent_id = client.get(f"{AGENT}/api/v1/query_ai_agent_config_list").json()["data"][0]["agentId"]
    body = client.get(f"{AGENT}/api/v1/agent_team", params={"agentId": agent_id}).json()
    assert_response_ok(body)
    return body["data"]


def test_extended_experts_registered(client: httpx.Client):
    """立项扩展专家已装配：出现在 agent_team 且职能描述非空。"""
    team = _team(client)
    names = {e["name"] for e in team["experts"]}
    assert EXTENDED_EXPERTS <= names, f"缺少扩展专家: {EXTENDED_EXPERTS - names}"
    for e in team["experts"]:
        if e["name"] in EXTENDED_EXPERTS:
            assert e.get("description"), e


@pytest.mark.parametrize("expert", sorted(EXTENDED_EXPERTS))
def test_extended_expert_session(client: httpx.Client, expert: str, suffix: str):
    """扩展专家可独立建会话（RunnerNode 自动注册单独对话入口）。"""
    r = client.post(f"{AGENT}/api/v1/create_session",
                    json={"agentId": expert, "userId": f"ext_{suffix}"})
    assert r.status_code == 200
    body = r.json()
    assert_response_ok(body)
    assert body["data"]["sessionId"], body


def test_expert_team_consistency(client: httpx.Client):
    """专家团与装配一致：memberCount = 装配专家数；默认权重合计恰为 100。"""
    team = _team(client)
    cfg = client.get(f"{AGENT}/api/v1/expert_team/config",
                     params={"userId": "consistency_check"}).json()
    assert_response_ok(cfg)
    assert cfg["data"]["memberCount"] == len(team["experts"]), cfg
    total = sum(int(m["weight"]) for m in cfg["data"]["members"])
    assert total == 100, f"默认权重合计应为 100，实际 {total}"
    member_keys = {m["key"] for m in cfg["data"]["members"]}
    assert member_keys == {e["name"] for e in team["experts"]}, "权重面板成员应与装配专家一致"


def test_query_stock_news_tool_data_path():
    """舆情工具数据链路（不经 LLM）：8080 internal 行情聚合的 news 部分可解析。

    直连主服务 internal 端点（queryStockNews 的底层来源），断言 news 为列表
    （外网受限时可能为空列表，但结构必须合法）。
    """
    r = httpx.get(f"{MAIN}/api/internal/market/realtime",
                  params={"market": "sh", "code": "600519", "recentNewsSize": 3,
                          "includeMinute": False},
                  headers={"X-Internal-Token": INTERNAL_TOKEN}, timeout=30)
    body = r.json()
    assert body["code"] == 200, body
    assert isinstance(body["data"].get("news"), list), body["data"]
