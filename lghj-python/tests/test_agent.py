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


def test_create_session_post_and_get_idempotent(client: httpx.Client, suffix: str):
    """create_session（GET/POST 双契约）：返回 sessionId；同 userId 幂等复用同一会话。"""
    r = client.get(f"{AGENT}/api/v1/query_ai_agent_config_list")
    agent_id = r.json()["data"][0]["agentId"]
    user_id = f"f7sess_{suffix}"

    r = client.post(f"{AGENT}/api/v1/create_session", json={"agentId": agent_id, "userId": user_id})
    assert r.status_code == 200
    body = r.json()
    assert_response_ok(body)
    session_id = body["data"]["sessionId"]
    assert isinstance(session_id, str) and session_id, "应返回 sessionId"

    # POST 再次创建（同 userId）→ 幂等
    r = client.post(f"{AGENT}/api/v1/create_session", json={"agentId": agent_id, "userId": user_id})
    assert r.json()["data"]["sessionId"] == session_id, "同 userId 应幂等复用会话"

    # GET 契约
    r = client.get(f"{AGENT}/api/v1/create_session", params={"agentId": agent_id, "userId": user_id})
    assert r.status_code == 200
    assert_response_ok(r.json())
    assert r.json()["data"]["sessionId"] == session_id, "GET 与 POST 应返回同一会话"


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
