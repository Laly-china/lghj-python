"""契约自测：agent.js（Agent 服务 8091）+ 内部 API（8080 /api/internal/*，X-Internal-Token）
+ 端到端工具链（8091 chat → X-Internal-Token → 8080 internal 工具）。

响应体：Response{code:"0000", info, data}；错误码 E0001/0001/0002。
LLM 真调（DEEPSEEK_API_KEY），断言避免过死：内容非空 + 工具链路以 8080 访问日志佐证。
"""

from __future__ import annotations

import os
import time

import httpx

from conftest import AGENT, INTERNAL_TOKEN, MAIN, assert_response_ok, log_size, read_log_tail

LOG_8080 = os.path.join(os.path.dirname(__file__), "run-8080.log")


# ====================== 智能体配置与会话 ======================

def test_query_agent_config_list(client: httpx.Client):
    """GET /api/v1/query_ai_agent_config_list：code="0000"，data[{agentId,agentName,agentDesc}]。"""
    r = client.get(f"{AGENT}/api/v1/query_ai_agent_config_list")
    assert r.status_code == 200
    body = r.json()
    assert_response_ok(body)
    configs = body["data"]
    assert isinstance(configs, list) and configs, "应至少配置一个智能体"
    for field in ("agentId", "agentName", "agentDesc"):
        assert field in configs[0], f"配置项缺字段 {field}: {configs[0]}"


def test_create_session_post_and_get_fresh(client: httpx.Client, suffix: str):
    """create_session（GET/POST 双契约）：每次调用都新建会话。

    原 Java 为同 userId 幂等复用；本工程扩展历史落库后改为每次新建，
    否则多轮「新建对话」都折进同一历史行（标题停在首问、列表无新增）。
    """
    r = client.get(f"{AGENT}/api/v1/query_ai_agent_config_list")
    agent_id = r.json()["data"][0]["agentId"]
    user_id = f"f7sess_{suffix}"

    r = client.post(f"{AGENT}/api/v1/create_session", json={"agentId": agent_id, "userId": user_id})
    assert r.status_code == 200
    body = r.json()
    assert_response_ok(body)
    session_id = body["data"]["sessionId"]
    assert isinstance(session_id, str) and session_id, "应返回 sessionId"

    # POST 再次创建 → 新会话（每次新建，配合「新建对话」语义）
    r = client.post(f"{AGENT}/api/v1/create_session", json={"agentId": agent_id, "userId": user_id})
    second_id = r.json()["data"]["sessionId"]
    assert second_id and second_id != session_id, "每次 create_session 应新建会话"

    # GET 契约
    r = client.get(f"{AGENT}/api/v1/create_session", params={"agentId": agent_id, "userId": user_id})
    assert r.status_code == 200
    assert_response_ok(r.json())
    assert r.json()["data"]["sessionId"], "GET 契约同样应返回 sessionId"


def test_create_session_bad_agent_id(client: httpx.Client, suffix: str):
    """不存在的 agentId：code=E0001（智能体ID不存在）。"""
    r = client.post(f"{AGENT}/api/v1/create_session",
                    json={"agentId": "no-such-agent-f7", "userId": f"f7bad_{suffix}"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "E0001", f"应返回 E0001: {body}"


# ====================== 内部 API 鉴权（8080，X-Internal-Token） ======================

def test_internal_token_correct(client: httpx.Client, trader_user: dict):
    """正确 X-Internal-Token：聚合行情数据（quote/minuteData/news 结构）。"""
    r = client.get(f"{MAIN}/api/internal/market/realtime",
                   params={"code": "600519", "recentNewsSize": 2},
                   headers={"X-Internal-Token": INTERNAL_TOKEN})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 200, body
    data = body["data"]
    for field in ("market", "code", "queryTime", "quote", "minuteData", "news"):
        assert field in data, f"聚合行情缺字段 {field}"
    assert data["market"] == "sh" and data["code"] == "600519"
    assert data["quote"] and float(data["quote"]["price"]) > 0
    assert isinstance(data["news"], list) and len(data["news"]) <= 2


def test_internal_token_wrong_and_missing(client: httpx.Client):
    """错误/缺失 token：code=500 msg="internal token invalid"（HTTP 200，照抄原 Spring 语义）。"""
    for headers in ({"X-Internal-Token": "wrong-token"}, {}):
        r = client.get(f"{MAIN}/api/internal/market/realtime", params={"code": "600519"}, headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == 500, f"应返回 code 500: {body}"
        assert body["msg"] == "internal token invalid"


def test_internal_market_param_semantics(client: httpx.Client):
    """market 缺省按代码推断（6 开头→sh）；code 缺失→500；空白 code→"stock code required"。"""
    headers = {"X-Internal-Token": INTERNAL_TOKEN}
    # 000001 → sz 推断
    r = client.get(f"{MAIN}/api/internal/market/realtime",
                   params={"code": "000001", "includeMinute": "false"}, headers=headers)
    assert r.json()["code"] == 200
    assert r.json()["data"]["market"] == "sz"

    # code 完全缺失 → SYSTEM_ERROR
    r = client.get(f"{MAIN}/api/internal/market/realtime", headers=headers)
    assert r.json()["code"] == 500

    # code 空白 → "stock code required"
    r = client.get(f"{MAIN}/api/internal/market/realtime", params={"code": "  "}, headers=headers)
    assert r.json()["msg"] == "stock code required"


def test_internal_sim_trade_profile(client: httpx.Client, trader_user: dict):
    """内部交易画像：有交易用户字段齐全；无交易用户 behaviorTags=[NO_TRADE_RECORD]。"""
    r = client.get(f"{MAIN}/api/internal/sim-trade/profile",
                   params={"userId": trader_user["id"]},
                   headers={"X-Internal-Token": INTERNAL_TOKEN})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 200, body
    profile = body["data"]
    # 结构：{userId, account, positions, recentOrders, recentDeals, summary}
    for field in ("userId", "account", "positions", "recentOrders", "recentDeals", "summary"):
        assert field in profile, f"画像缺字段 {field}"
    # behaviorTags 在 summary 内（照原 Summary 字段声明）
    assert "behaviorTags" in profile["summary"], f"summary 应含 behaviorTags: {profile['summary']}"
    assert isinstance(profile["summary"]["behaviorTags"], list)
    # 有交易用户：持仓/委托/成交可见
    assert profile["positions"], "已成交用户应有持仓"
    assert profile["recentOrders"], "已成交用户应有委托单"

    # 无交易用户（刚注册未建户未交易）→ behaviorTags=[NO_TRADE_RECORD]
    r = client.get(f"{MAIN}/api/internal/sim-trade/profile", params={"userId": 999999999},
                   headers={"X-Internal-Token": INTERNAL_TOKEN})
    assert r.json()["code"] == 200
    assert r.json()["data"]["summary"]["behaviorTags"] == ["NO_TRADE_RECORD"]

    # userId 缺失 → 500
    r = client.get(f"{MAIN}/api/internal/sim-trade/profile",
                   headers={"X-Internal-Token": INTERNAL_TOKEN})
    assert r.json()["code"] == 500


# ====================== 端到端：chat 真调 + 工具链（8091 → 8080） ======================

def test_chat_nonempty_content(client: httpx.Client, suffix: str):
    """POST /api/v1/chat（LLM 真调）：code="0000"，data.content 非空字符串。"""
    r = client.get(f"{AGENT}/api/v1/query_ai_agent_config_list")
    agent_id = r.json()["data"][0]["agentId"]
    r = client.post(f"{AGENT}/api/v1/create_session",
                    json={"agentId": agent_id, "userId": f"f7chat_{suffix}"})
    session_id = r.json()["data"]["sessionId"]

    r = client.post(f"{AGENT}/api/v1/chat",
                    json={"agentId": agent_id, "userId": f"f7chat_{suffix}",
                          "sessionId": session_id, "message": "请用一句话介绍你自己，不要调用任何工具。"},
                    timeout=180.0)
    assert r.status_code == 200, r.text
    body = r.json()
    assert_response_ok(body)
    content = body["data"]["content"]
    assert isinstance(content, str) and content.strip(), f"chat 内容不应为空: {body}"


def test_chat_toolchain_via_internal_api(client: httpx.Client, trader_user: dict, suffix: str):
    """端到端工具链：agent 回答"我的持仓/画像"问题时应真实调 8080 /api/internal/*。

    userId 用 trader_user 的数字 id 字符串（前端 Prediction.vue 即 String(info.id)），
    使画像工具能真实取到该用户的交易数据（trader_user 有账户与成交记录）。
    验证方式：记录 8080 访问日志偏移 → chat → 检查日志增量包含 /api/internal/。
    """
    offset = log_size(LOG_8080)
    agent_id = client.get(f"{AGENT}/api/v1/query_ai_agent_config_list").json()["data"][0]["agentId"]
    user_key = str(trader_user["id"])  # 前端语义：String(info.id)
    r = client.post(f"{AGENT}/api/v1/create_session",
                    json={"agentId": agent_id, "userId": user_key})
    session_id = r.json()["data"]["sessionId"]

    r = client.post(f"{AGENT}/api/v1/chat",
                    json={"agentId": agent_id, "userId": user_key, "sessionId": session_id,
                          "message": "请调用工具查询我的模拟交易画像，并简要说明我是否有交易记录、持仓情况如何。"},
                    timeout=180.0)
    assert r.status_code == 200, r.text
    body = r.json()
    assert_response_ok(body)
    content = body["data"]["content"]
    assert isinstance(content, str) and content.strip(), "chat 内容不应为空"

    # 工具链路佐证：8080 访问日志应出现 /api/internal/sim-trade/profile
    time.sleep(1.0)
    tail = read_log_tail(LOG_8080, offset)
    assert "/api/internal/sim-trade/profile" in tail, \
        "8080 日志中未发现画像工具调用——端到端工具链未发生"


def test_chat_stream_nonempty(client: httpx.Client, suffix: str):
    """POST /api/v1/chat_stream：HTTP 200 text/plain chunked，流式内容非空。"""
    agent_id = client.get(f"{AGENT}/api/v1/query_ai_agent_config_list").json()["data"][0]["agentId"]
    user_key = f"f7stream_{suffix}"
    r = client.post(f"{AGENT}/api/v1/create_session", json={"agentId": agent_id, "userId": user_key})
    session_id = r.json()["data"]["sessionId"]

    chunks: list[str] = []
    with client.stream("POST", f"{AGENT}/api/v1/chat_stream",
                       json={"agentId": agent_id, "userId": user_key,
                             "sessionId": session_id,
                             "message": "请用一句话说明风险提示。不要调用工具。"},
                       timeout=180.0) as resp:
        assert resp.status_code == 200
        ctype = resp.headers.get("content-type", "")
        assert "text/plain" in ctype, f"流式 content-type 应为 text/plain: {ctype}"
        for chunk in resp.iter_text():
            chunks.append(chunk)
    body = "".join(chunks)
    assert body.strip(), "SSE/文本流不应为空"


# ====================== 扩展接口：Agent 流程可视化（trace / agent_team） ======================

def test_agent_team_endpoint(client: httpx.Client):
    """GET /api/v1/agent_team：团队结构 = 队长 + 6 专家（含职能描述）+ 本地工具名。"""
    agent_id = client.get(f"{AGENT}/api/v1/query_ai_agent_config_list").json()["data"][0]["agentId"]
    r = client.get(f"{AGENT}/api/v1/agent_team", params={"agentId": agent_id})
    assert r.status_code == 200
    body = r.json()
    assert_response_ok(body)
    team = body["data"]
    assert team["supervisor"]["name"] == "InvestmentAdvisorSupervisor"
    assert {e["name"] for e in team["experts"]} == {
        "MarketAnalysisAgent", "QuantTechnicalAgent", "PersonalTradeProfileAgent",
        "RiskAssessmentAgent", "PortfolioAdviceAgent", "ComplianceDisclosureAgent",
    }, f"应有 6 个专家: {team['experts']}"
    for e in team["experts"]:
        assert e.get("description"), f"专家职能描述不应为空: {e}"
    assert {"querySimTradeProfile", "queryRealtimeMarket"} <= set(team["tools"])


def test_trace_endpoint_structure(client: httpx.Client, suffix: str):
    """chat 后 GET /api/v1/trace：事件列表结构（run_start 边界 + agent_text + 公共字段与合法 type）。"""
    agent_id = client.get(f"{AGENT}/api/v1/query_ai_agent_config_list").json()["data"][0]["agentId"]
    user_id = f"f7trace_{suffix}"
    r = client.post(f"{AGENT}/api/v1/create_session", json={"agentId": agent_id, "userId": user_id})
    session_id = r.json()["data"]["sessionId"]

    r = client.post(f"{AGENT}/api/v1/chat",
                    json={"agentId": agent_id, "userId": user_id, "sessionId": session_id,
                          "message": "请用一句话介绍你自己，不要调用任何工具。"},
                    timeout=180.0)
    assert_response_ok(r.json())

    r = client.get(f"{AGENT}/api/v1/trace",
                   params={"agentId": agent_id, "userId": user_id, "sessionId": session_id})
    assert r.status_code == 200
    body = r.json()
    assert_response_ok(body)
    events = body["data"]
    assert isinstance(events, list) and events, "trace 不应为空"
    assert events[0]["type"] == "run_start", f"首事件应为 run_start: {events[0]}"
    assert any(e["type"] == "agent_text" for e in events), "应记录最终文本输出"
    for e in events:
        for field in ("seq", "ts", "type", "agent"):
            assert field in e, f"轨迹事件缺公共字段 {field}: {e}"
        assert e["type"] in ("run_start", "llm_call", "transfer", "tool", "agent_text"), \
            f"非法事件类型: {e}"


def test_trace_records_tool_call(client: httpx.Client, trader_user: dict, suffix: str):
    """画像类问题的 trace 应记录 querySimTradeProfile 工具调用（断言放宽，LLM 行为有波动）。

    真实 LLM 可能经 transfer 转交专家后调工具，也可能由 Supervisor 直接调用
    （工具挂在共享 ChatModel 上，两条路径均合法），故 transfer 不做硬断言。
    """
    agent_id = client.get(f"{AGENT}/api/v1/query_ai_agent_config_list").json()["data"][0]["agentId"]
    user_key = str(trader_user["id"])  # 前端语义：String(info.id)
    r = client.post(f"{AGENT}/api/v1/create_session", json={"agentId": agent_id, "userId": user_key})
    session_id = r.json()["data"]["sessionId"]
    r = client.post(f"{AGENT}/api/v1/chat",
                    json={"agentId": agent_id, "userId": user_key, "sessionId": session_id,
                          "message": "请调用工具查询我的模拟交易画像，并说明我是否有交易记录。"},
                    timeout=180.0)
    assert_response_ok(r.json())

    r = client.get(f"{AGENT}/api/v1/trace",
                   params={"agentId": agent_id, "userId": user_key, "sessionId": session_id})
    events = r.json()["data"]
    tool_events = [e for e in events if e["type"] == "tool" and e.get("name") == "querySimTradeProfile"]
    assert tool_events, f"trace 应记录 querySimTradeProfile 工具调用: {[e['type'] for e in events]}"
    assert tool_events[0].get("args", {}).get("userId") == user_key, "工具入参应记录 userId"
    assert tool_events[0].get("durationMs") is not None, "工具调用应记录耗时"
    # transfer 出现时结构必须合法（目标专家名非空），但不强制发生
    for e in events:
        if e["type"] == "transfer":
            assert e.get("name"), f"transfer 事件应记录目标专家: {e}"


# ====================== 扩展接口：专家独立对话 / 历史 / 知识库（原 Java 无） ======================

def test_expert_chat_and_history_persisted(client: httpx.Client, suffix: str):
    """专家可独立对话（agentId=专家名建会话+chat）→ 历史落库（history_list/history_messages）。"""
    agent_id = "QuantTechnicalAgent"
    user_id = f"f7expert_{suffix}"
    r = client.post(f"{AGENT}/api/v1/create_session", json={"agentId": agent_id, "userId": user_id})
    assert r.status_code == 200
    body = r.json()
    assert_response_ok(body), f"专家建会话应成功: {body}"
    session_id = body["data"]["sessionId"]

    r = client.post(f"{AGENT}/api/v1/chat",
                    json={"agentId": agent_id, "userId": user_id, "sessionId": session_id,
                          "message": "请用一句话解释什么是均线。"},
                    timeout=180.0)
    assert r.status_code == 200
    body = r.json()
    assert_response_ok(body)
    assert (body["data"]["content"] or "").strip(), "专家 chat 内容不应为空"

    # 历史落库：列表含该会话（标题取首条提问），消息 ≥ 2 条（user+assistant）
    r = client.get(f"{AGENT}/api/v1/history_list", params={"userId": user_id})
    assert_response_ok(r.json())
    sessions = r.json()["data"]
    hit = next((s for s in sessions if s["sessionId"] == session_id), None)
    assert hit is not None, f"历史列表应含该会话: {sessions}"
    assert hit["agentId"] == agent_id
    assert hit["title"], "会话标题应取首条提问"

    r = client.get(f"{AGENT}/api/v1/history_messages", params={"sessionId": session_id})
    assert_response_ok(r.json())
    messages = r.json()["data"]
    assert len(messages) >= 2, f"应至少落库 user+assistant 两条消息: {messages}"
    assert messages[0]["role"] == "user"
    assert messages[-1]["role"] == "assistant"
    assert "trace" in messages[-1], "assistant 消息应附执行轨迹"

    # 清理：删除历史会话
    r = client.delete(f"{AGENT}/api/v1/history_session",
                      params={"sessionId": session_id, "userId": user_id})
    assert_response_ok(r.json())
    assert r.json()["data"]["deleted"] is True


def test_kb_upload_list_delete(client: httpx.Client, suffix: str):
    """知识库全流程：上传 txt/md → 列表可见 → 删除（逻辑删除）。"""
    user_id = f"f7kb_{suffix}"
    filename = f"测试纪律-{suffix}.md"
    r = client.post(f"{AGENT}/api/v1/kb_upload",
                    data={"userId": user_id},
                    files={"file": (filename, "第一条：止损幅度不超过8%。".encode("utf-8"),
                                    "text/markdown")})
    assert r.status_code == 200
    body = r.json()
    assert_response_ok(body)
    assert body["data"]["docId"] > 0
    assert body["data"]["charCount"] > 0

    r = client.get(f"{AGENT}/api/v1/kb_list", params={"userId": user_id})
    assert_response_ok(r.json())
    docs = r.json()["data"]
    assert len(docs) == 1 and docs[0]["title"] == f"测试纪律-{suffix}", f"列表应含刚上传文档: {docs}"

    doc_id = docs[0]["id"]
    r = client.delete(f"{AGENT}/api/v1/kb_doc", params={"docId": doc_id, "userId": user_id})
    assert_response_ok(r.json())
    assert r.json()["data"]["deleted"] is True

    r = client.get(f"{AGENT}/api/v1/kb_list", params={"userId": user_id})
    assert r.json()["data"] == [], "删除后列表应为空"
