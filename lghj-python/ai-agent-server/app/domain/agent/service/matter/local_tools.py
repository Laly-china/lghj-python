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

from app.domain.agent.adapter.port import FundFlowPort, KbSearchPort, MarketDataPort, SimTradeProfilePort
from app.domain.agent.service.armory.runtime import ToolSpec

# 原 Java InvestmentTradeProfileMcpServerConfig 中的两个本地 MCP bean 名（yml local.name 引用）
INVESTMENT_TRADE_PROFILE_MCP = "investmentTradeProfileMcp"
MARKET_REALTIME_MCP = "marketRealtimeMcp"
# 本工程扩展的第三个本地工具 bean 名（知识库检索，原 Java 无）
KNOWLEDGE_BASE_MCP = "knowledgeBaseMcp"
# 立项扩展工具 bean 名：个股新闻舆情（供舆情/事件分析 Agent，复用行情聚合接口的 news 部分）
STOCK_NEWS_MCP = "stockNewsMcp"
# 立项扩展工具 bean 名：个股资金流向（供资金流向 Agent）
FUND_FLOW_MCP = "fundFlowMcp"


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


def build_knowledge_base_tool(kb_port: "KbSearchPort | None") -> ToolSpec | None:
    """构造 queryKnowledgeBase 工具（本工程扩展，原 Java 无）。

    检索当前用户上传到个人知识库的文档；kb_port 未注入时返回 None（不注册）。
    """

    if kb_port is None:
        return None

    def handler(args: dict[str, Any]) -> dict[str, Any]:
        args = args or {}
        user_id = str(args.get("userId") or "")
        query = str(args.get("query") or "")
        # 1. 参数校验：用户ID / 检索词为空
        if not user_id.strip():
            return {"success": False, "message": "缺少当前用户ID，无法检索个人知识库。"}
        if not query.strip():
            return {"success": False, "message": "缺少检索关键词，无法检索个人知识库。"}
        # 2. 检索（端口层实现，失败由端口/存储层抛出）
        try:
            results = kb_port.search(user_id.strip(), query.strip(), limit=5)
        except Exception:  # noqa: BLE001 检索异常降级为失败结果
            return {"success": False, "message": "知识库检索失败，可能是存储不可用。"}
        # 3. 无命中
        if not results:
            return {"success": False, "message": "知识库中没有与该关键词相关的内容。"}
        # 4. 成功：返回标题+片段（截断防止撑爆上下文）
        clipped = [
            {"title": r["title"], "snippet": r["snippet"][:300]} for r in results
        ]
        return {"success": True, "message": "OK", "results": clipped}

    return ToolSpec(
        name="queryKnowledgeBase",
        description=(
            "检索当前用户上传到个人知识库的文档内容（按关键词返回相关段落）。"
            "当用户提到'我的知识库''我上传的资料/文档''根据我给的资料'等问题时必须调用。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索关键词，从用户问题中提取的主题词或短语。",
                },
                "userId": {
                    "type": "string",
                    "description": "当前对话用户ID。必须使用系统上下文中的当前用户ID，不要编造。",
                },
            },
            "required": ["query", "userId"],
        },
        handler=handler,
    )


def build_query_stock_news_tool(port: MarketDataPort) -> ToolSpec:
    """构造 queryStockNews 工具（立项扩展：舆情/事件分析 Agent 的新闻数据源，原 Java 无）。

    复用行情聚合端口（includeMinute=False 只取资讯），解析出 data.news 单独返回，
    避免舆情 Agent 在行情大 JSON 里捞新闻。
    """

    def handler(args: dict[str, Any]) -> dict[str, Any]:
        import json as _json

        args = args or {}
        raw_code = args.get("code") or ""
        if not isinstance(raw_code, str) or not raw_code.strip():
            return {"success": False, "message": "缺少股票代码，无法查询新闻舆情。"}

        code = raw_code.strip()
        raw_market = args.get("market")
        market = raw_market.strip().lower() if isinstance(raw_market, str) and raw_market.strip() else _infer_market(code)
        # recentN：默认 10，夹在 [1, 20]
        raw_n = args.get("recentN")
        recent_n = 10 if raw_n is None else max(1, min(int(raw_n), 20))

        market_json = port.query_realtime_market_json(market, code, recent_n, False)
        if not market_json or not market_json.strip():
            return {"success": False, "message": "未获取到新闻资讯，可能是资讯源、主后端或股票代码不可用。"}
        try:
            body = _json.loads(market_json)
            news = (body.get("data") or {}).get("news") or []
        except (ValueError, AttributeError):
            return {"success": False, "message": "新闻资讯响应解析失败，请稍后重试。"}
        if not news:
            return {"success": False, "message": "该股票近期没有检索到相关新闻资讯。"}
        return {"success": True, "message": "OK", "count": len(news), "news": news}

    return ToolSpec(
        name="queryStockNews",
        description=(
            "查询A股个股最近新闻资讯列表（标题、摘要、发布时间、来源、链接）。"
            "分析市场舆情、舆论倾向、媒体热度，或从新闻中识别影响股价的事件时必须调用。"
        ),
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
                "recentN": {
                    "type": "integer",
                    "description": "返回新闻条数，默认10，最大20。",
                },
            },
            "required": ["code"],
        },
        handler=handler,
    )


def build_query_fund_flow_tool(port: FundFlowPort) -> ToolSpec:
    """构造 queryFundFlow 工具（立项扩展：资金流向 Agent 数据源，原 Java 无）。

    返回个股近 N 日资金流（主力/超大/大/中/小单净额与净占比），金额单位元。
    """

    def handler(args: dict[str, Any]) -> dict[str, Any]:
        import json as _json

        args = args or {}
        raw_code = args.get("code") or ""
        if not isinstance(raw_code, str) or not raw_code.strip():
            return {"success": False, "message": "缺少股票代码，无法查询资金流向。"}

        code = raw_code.strip()
        raw_market = args.get("market")
        market = raw_market.strip().lower() if isinstance(raw_market, str) and raw_market.strip() else _infer_market(code)
        # days：默认 5，夹在 [1, 10]（足够判断趋势，控制上下文长度）
        raw_days = args.get("days")
        days = 5 if raw_days is None else max(1, min(int(raw_days), 10))

        flow_json = port.query_fundflow_json(market, code, days)
        if not flow_json or not flow_json.strip():
            return {"success": False, "message": "未获取到资金流向数据，可能是数据源、主后端或股票代码不可用。"}
        try:
            body = _json.loads(flow_json)
            items = (body.get("data") or {}).get("items") or []
        except (ValueError, AttributeError):
            return {"success": False, "message": "资金流向响应解析失败，请稍后重试。"}
        if not items:
            return {"success": False, "message": "该股票暂无资金流向数据。"}
        return {"success": True, "message": "OK", "count": len(items), "fundFlow": items}

    return ToolSpec(
        name="queryFundFlow",
        description=(
            "查询A股个股近N日资金流向（主力/超大单/大单/中单/小单净流入金额与占比，最新交易日在前）。"
            "分析主力资金动向、资金进出、大单行为时必须调用。"
        ),
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
                "days": {
                    "type": "integer",
                    "description": "返回最近交易日天数，默认5，最大10。",
                },
            },
            "required": ["code"],
        },
        handler=handler,
    )


def build_local_tool_registry(
    market_data_port: MarketDataPort,
    sim_trade_profile_port: SimTradeProfilePort,
    kb_search_port: "KbSearchPort | None" = None,
    fund_flow_port: "FundFlowPort | None" = None,
) -> dict[str, list[ToolSpec]]:
    """本地工具注册表：bean 名 -> 工具列表（对应原 Java @Bean("xxxMcp") ToolCallbackProvider）。

    装配链 ChatModelNode 依据 yml tool-mcp-list 中的 local.name 从这里取工具；
    knowledgeBaseMcp / stockNewsMcp / fundFlowMcp 为本工程扩展。
    """
    registry: dict[str, list[ToolSpec]] = {
        INVESTMENT_TRADE_PROFILE_MCP: [build_query_sim_trade_profile_tool(sim_trade_profile_port)],
        MARKET_REALTIME_MCP: [build_query_realtime_market_tool(market_data_port)],
        STOCK_NEWS_MCP: [build_query_stock_news_tool(market_data_port)],
    }
    if fund_flow_port is not None:
        registry[FUND_FLOW_MCP] = [build_query_fund_flow_tool(fund_flow_port)]
    kb_tool = build_knowledge_base_tool(kb_search_port)
    if kb_tool is not None:
        registry[KNOWLEDGE_BASE_MCP] = [kb_tool]
    return registry
