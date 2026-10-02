"""matter 本地工具：query_realtime_market / query_sim_trade_profile。

复现自原 Java 类（LLM 可调用的本地 MCP 工具服务）：
    ai-agent-scaffoid-feng-domain/.../armory/matter/mcp/server/MarketRealtimeMcpService.java
    ai-agent-scaffoid-feng-domain/.../armory/matter/mcp/server/InvestmentTradeProfileMcpService.java
    ai-agent-scaffoid-feng-domain/.../armory/matter/mcp/server/InvestmentTradeProfileMcpServerConfig.java
        （bean 名：marketRealtimeMcp / investmentTradeProfileMcp，与装配 yml tool-mcp-list 对应）

工具名、描述、参数说明、响应字段（success/message/marketJson/profileJson）
与错误文案均严格照抄原 Java 注解文本。
"""

from __future__ import annotations

from typing import Any

from app.domain.agent.adapter.port import MarketDataPort, SimTradeProfilePort
from app.domain.agent.service.armory.runtime import ToolSpec

# 原 Java InvestmentTradeProfileMcpServerConfig 中的两个本地 MCP bean 名（yml local.name 引用）
INVESTMENT_TRADE_PROFILE_MCP = "investmentTradeProfileMcp"
MARKET_REALTIME_MCP = "marketRealtimeMcp"


# ====================== 工具一：查询模拟交易画像 ======================

def build_query_sim_trade_profile_tool(port: SimTradeProfilePort) -> ToolSpec:
    """构造 querySimTradeProfile 工具（照抄原 Java @Tool 与参数描述）。"""

    def handler(args: dict[str, Any]) -> dict[str, Any]:
        user_id = (args or {}).get("userId") or ""
        # 1. 参数校验：用户ID为空
        if not isinstance(user_id, str) or not user_id.strip():
            return {"success": False, "message": "缺少当前用户ID，无法查询模拟交易画像。"}
        # 2. 调用端口层，远程获取画像 JSON
        profile_json = port.query_profile_json(user_id.strip())
        # 3. 结果校验：未获取到有效画像
        if not profile_json or not profile_json.strip():
            return {"success": False, "message": "未获取到模拟交易画像，可能是账户不存在、暂无交易记录或交易系统不可用。"}
        # 4. 成功
        return {"success": True, "message": "OK", "profileJson": profile_json}

    return ToolSpec(
        name="querySimTradeProfile",
        description="根据当前用户ID查询量股化金模拟交易画像，包括账户、持仓、近期委托、近期成交、交易行为标签和仓位集中度。只用于个性化投资顾问分析。",
        parameters={
            "type": "object",
            "properties": {
                "userId": {
                    "type": "string",
                    "description": "当前对话用户ID。必须使用系统上下文中的当前用户ID，不要编造或改查其他用户。",
                },
            },
            "required": ["userId"],
        },
        handler=handler,
    )


# ====================== 工具二：查询实时行情 ======================

def _infer_market(code: str) -> str:
    """照抄原 Java inferMarket：5/6/9 开头视为上海，其余深圳。"""
    if code.startswith(("5", "6", "9")):
        return "sh"
    return "sz"


def build_query_realtime_market_tool(port: MarketDataPort) -> ToolSpec:
    """构造 queryRealtimeMarket 工具（照抄原 Java @Tool 与参数描述）。"""

    def handler(args: dict[str, Any]) -> dict[str, Any]:
        args = args or {}
        raw_code = args.get("code") or ""
        # 参数校验：缺少股票代码
        if not isinstance(raw_code, str) or not raw_code.strip():
            return {"success": False, "message": "缺少股票代码，无法查询实时行情。"}

        code = raw_code.strip()
        raw_market = args.get("market")
        market = raw_market.strip().lower() if isinstance(raw_market, str) and raw_market.strip() else _infer_market(code)
        # recentNewsSize：默认 5，夹在 [0, 20]（对齐原 Java Math.max/min 逻辑）
        raw_news = args.get("recentNewsSize")
        news_size = 5 if raw_news is None else max(0, min(int(raw_news), 20))
        # includeMinute：默认 True
        raw_minute = args.get("includeMinute")
        include_minute = True if raw_minute is None else bool(raw_minute)

        market_json = port.query_realtime_market_json(market, code, news_size, include_minute)
        if not market_json or not market_json.strip():
            return {"success": False, "message": "未获取到实时行情，可能是行情源、主后端或股票代码不可用。"}
        return {"success": True, "message": "OK", "marketJson": market_json}

    return ToolSpec(
        name="queryRealtimeMarket",
        description="查询A股实时行情、当日分时和最近资讯。用户询问现在价格、涨跌幅、今日走势、实时行情、最新新闻时必须调用。",
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "A股股票代码，例如 600519、000001。不要带市场前缀。",
                },
                "market": {
                    "type": "string",
                    "description": "市场代码，上海填 sh，深圳填 sz。未知可不填，工具会根据股票代码推断。",
                },
                "recentNewsSize": {
                    "type": "integer",
                    "description": "最近资讯条数，默认5，最大20。",
                },
                "includeMinute": {
                    "type": "boolean",
                    "description": "是否返回当日分时数据，默认 true。只问新闻时可填 false。",
                },
            },
            "required": ["code"],
        },
        handler=handler,
    )


def build_local_tool_registry(
    market_data_port: MarketDataPort,
    sim_trade_profile_port: SimTradeProfilePort,
) -> dict[str, list[ToolSpec]]:
    """本地工具注册表：bean 名 -> 工具列表（对应原 Java 两个 @Bean("xxxMcp") ToolCallbackProvider）。

    装配链 ChatModelNode 依据 yml tool-mcp-list 中的 local.name 从这里取工具。
    """
    return {
        INVESTMENT_TRADE_PROFILE_MCP: [build_query_sim_trade_profile_tool(sim_trade_profile_port)],
        MARKET_REALTIME_MCP: [build_query_realtime_market_tool(market_data_port)],
    }
