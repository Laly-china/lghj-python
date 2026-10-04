# -*- coding: utf-8 -*-
"""api.py —— 三后端 API 客户端（量股化金 Streamlit 前端）

对接契约（与原 Vue 前端 request.js 拦截器语义一致）：
- 主服务 8080：Result{code, msg, data}，成功码 200（数字），鉴权头名 token
- Agent 服务 8091：Response{code, info, data}，成功码 "0000"（字符串）
- 预测服务 8001：裸 JSON（分时数组 / {symbol, predictions} 对象）

服务地址可用环境变量覆盖：LGHJ_MAIN_URL / LGHJ_AGENT_URL / LGHJ_PRED_URL
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pandas as pd
import streamlit as st

MAIN = os.environ.get("LGHJ_MAIN_URL", "http://127.0.0.1:8080")
AGENT = os.environ.get("LGHJ_AGENT_URL", "http://127.0.0.1:8091")
PRED = os.environ.get("LGHJ_PRED_URL", "http://127.0.0.1:8001")


@st.cache_resource
def http() -> httpx.Client:
    """共享 HTTP 客户端（连接复用）。"""
    return httpx.Client(timeout=20)


def _headers() -> dict[str, str]:
    tok = st.session_state.get("token")
    return {"token": tok} if tok else {}


def _handle_401() -> None:
    """token 失效：清除会话并刷新（对应前端拦截器强制登出）。"""
    for key in ("token", "user"):
        st.session_state.pop(key, None)
    st.toast("登录已失效，请重新登录", icon=":material/logout:")
    st.rerun()


# ---------------- 主服务（Result 包装） ----------------

def main_api(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> tuple[bool, Any, str]:
    """调用 8080，返回 (ok, data, msg)。网络异常时 ok=False。"""
    try:
        r = http().request(
            method, MAIN + path, params=params, json=json_body, headers=_headers()
        )
    except httpx.HTTPError as e:
        return False, None, f"主服务连接失败（{e.__class__.__name__}），请确认 8080 已启动"
    if r.status_code == 401:
        _handle_401()
    try:
        body = r.json()
    except ValueError:
        return False, None, f"主服务响应异常 HTTP {r.status_code}"
    ok = body.get("code") == 200
    return ok, body.get("data"), body.get("msg") or ("" if ok else "操作失败")


# ---------------- Agent 服务（Response 包装） ----------------

def agent_api(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: httpx.Timeout | float | None = None,
) -> tuple[bool, Any, str]:
    """调用 8091，返回 (ok, data, info)；timeout 为 None 时用共享客户端默认 20s。"""
    try:
        r = http().request(
            method, AGENT + path, params=params, json=json_body, headers=_headers(),
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        return False, None, f"智能体服务连接失败（{e.__class__.__name__}），请确认 8091 已启动"
    try:
        body = r.json()
    except ValueError:
        return False, None, f"智能体服务响应异常 HTTP {r.status_code}"
    ok = body.get("code") == "0000"
    return ok, body.get("data"), body.get("info") or ""


# ---------------- 预测服务（裸 JSON） ----------------

def pred_api(path: str) -> tuple[bool, Any, str]:
    """调用 8001，返回 (ok, data, err)。

    预测/分时在数据源不可达时会先经历在线采集超时再回落本地缓存，
    单次可能耗时 60~90 秒，因此读超时单独放宽。
    """
    try:
        r = http().get(PRED + path, headers=_headers(), timeout=httpx.Timeout(150.0, connect=10.0))
    except httpx.HTTPError as e:
        return False, None, f"预测服务连接失败（{e.__class__.__name__}），请确认 8001 已启动"
    if r.status_code != 200:
        try:
            return False, None, r.json().get("msg") or f"HTTP {r.status_code}"
        except ValueError:
            return False, None, f"HTTP {r.status_code}"
    return True, r.json(), ""


# ---------------- 符号工具 ----------------

def split_symbol(symbol: str) -> tuple[str, str]:
    """'sh600519' -> ('sh', '600519')；裸 6 位代码按交易接口惯例不推断市场。"""
    s = (symbol or "").strip().lower()
    if len(s) == 8 and s[:2] in ("sh", "sz", "bj"):
        return s[:2], s[2:]
    return "", s


def make_symbol(market: str, code: str) -> str:
    return f"{(market or '').lower()}{code}"


# ---------------- 登录 / 注册 ----------------

def login(username: str, password: str) -> tuple[bool, str]:
    ok, data, msg = main_api("POST", "/api/login", json_body={"username": username, "password": password})
    if not ok:
        return False, msg or "用户名或密码错误"
    st.session_state.token = data["token"]
    st.session_state.user = data
    return True, f"欢迎回来，{data.get('username')}"


def register(username: str, password: str, nick_name: str = "", email: str = "", phone: str = "") -> tuple[bool, str]:
    body = {"username": username, "password": password}
    if nick_name:
        body["nickName"] = nick_name
    if email:
        body["email"] = email
    if phone:
        body["phone"] = phone
    ok, _d, msg = main_api("POST", "/api/register", json_body=body)
    return ok, msg or ("注册成功，请登录" if ok else "注册失败")


def logout() -> None:
    main_api("POST", "/api/logout")
    st.session_state.pop("token", None)
    st.session_state.pop("user", None)


# ---------------- 行情 / 股票 ----------------

def search_stocks(keyword: str) -> list[dict]:
    """股票搜索（LIKE 替代 ES，放行接口）。"""
    if not keyword.strip():
        return []
    ok, data, _m = main_api("GET", "/api/user/stock/search", params={"keyword": keyword.strip()})
    return data or []


@st.cache_data(ttl=5, max_entries=64)
def get_quote(market: str, code: str) -> dict | None:
    """实时行情八字段 {code,name,price,prevClose,open,volume,change,changePercent}。"""
    ok, data, _m = main_api(
        "GET", "/api/user/realtime/quote", params={"market": market, "code": code}
    )
    return data


@st.cache_data(ttl=300, max_entries=64)
def _kline_cached(symbol: str, period: str = "D") -> pd.DataFrame:
    ok, data, _m = main_api(
        "GET", "/api/user/stock/data", params={"symbol": symbol, "period": period}
    )
    df = pd.DataFrame(data or [])
    if not df.empty:
        df = df.sort_values("date").reset_index(drop=True)
    return df


def get_kline(symbol: str, period: str = "D") -> pd.DataFrame:
    """K线 {date,open,close,low,high}；空结果不缓存（首拉慢时会先返回空）。"""
    df = _kline_cached(symbol, period)
    if df.empty:
        _kline_cached.clear()
    return df


@st.cache_data(ttl=60, max_entries=32)
def get_minute(symbol: str) -> list[dict]:
    """当日分时（直连 8001；原 Vue 的 /api/ml 前缀是 vite 代理，真实路由无 /ml）。"""
    ok, data, _err = pred_api(f"/minute/{symbol}")
    return data or []


@st.cache_data(ttl=900, max_entries=32)
def get_predict(symbol: str) -> dict | None:
    """LSTM 未来 30 天预测 {symbol, predictions:[{date,price}]}。"""
    ok, data, _err = pred_api(f"/predict/{symbol}")
    return data


def get_news(symbol: str, recent_n: int = 20) -> list[dict]:
    """个股新闻（东财 JSONP，放行接口）。"""
    ok, data, _m = main_api(
        "GET", "/api/user/realtime/news", params={"symbol": symbol, "recentN": recent_n}
    )
    return data or []


# ---------------- 自选股 ----------------

def optional_list() -> list[dict]:
    ok, data, _m = main_api("GET", "/api/user/optional/list")
    return data or []


def optional_add(symbol: str) -> tuple[bool, str]:
    ok, _d, msg = main_api("POST", "/api/user/optional/add", params={"symbol": symbol})
    return ok, msg or ("添加成功" if ok else "添加失败")


def optional_remove(symbol: str) -> tuple[bool, str]:
    ok, _d, msg = main_api("POST", "/api/user/optional/remove", params={"symbol": symbol})
    return ok, msg or ("移除成功" if ok else "移除失败")


# ---------------- 账户 / 交易 ----------------

def account_create() -> tuple[bool, str]:
    ok, _d, msg = main_api("POST", "/api/user/account/create")
    return ok, msg or ("开户成功" if ok else "开户失败")


def account_info() -> dict | None:
    ok, data, _m = main_api("GET", "/api/user/account/query_info")
    return data


def positions() -> list[dict]:
    ok, data, _m = main_api("GET", "/api/user/account/query_positions")
    return data or []


def place_order(symbol: str, direction: int, price: float, quantity: int) -> tuple[bool, str]:
    """下单（query string 传参；quantity 单位为手）。"""
    ok, data, msg = main_api(
        "POST",
        "/api/user/trade/order",
        params={"symbol": symbol, "direction": direction, "price": price, "quantity": quantity},
    )
    if ok and isinstance(data, dict):
        return True, f"委托已提交：{data.get('orderNo', '')}"
    return False, msg or "下单失败"


def cancel_order(order_id: int) -> tuple[bool, str]:
    ok, _d, msg = main_api("POST", "/api/user/trade/cancel", params={"orderId": order_id})
    return ok, msg or ("撤单成功" if ok else "撤销失败")


def query_orders() -> list[dict]:
    ok, data, _m = main_api("GET", "/api/user/trade/query_orders")
    return data or []


def query_deals() -> list[dict]:
    ok, data, _m = main_api("GET", "/api/user/trade/query_deals")
    return data or []


# ---------------- 社区 ----------------

def blog_publish(title: str, context: str) -> tuple[bool, str]:
    """发布博客（字段名必须是 context，原系统契约）。"""
    ok, _d, msg = main_api("POST", "/api/user/blog", json_body={"title": title, "context": context})
    return ok, msg or ("发布成功" if ok else "发布失败")


def blog_page(kind: str, current: int = 1, size: int = 10, user_id: int | None = None) -> tuple[list[dict], int]:
    """博客列表。kind: hot/me/follow/user；返回 (records, total)。"""
    path = {
        "hot": "/api/user/blog/query/hot",
        "me": "/api/user/blog/query/of/me",
        "follow": "/api/user/blog/query/of/follow",
        "user": "/api/user/blog/query/of/user",
    }[kind]
    params: dict[str, Any] = {"current": current, "size": size}
    if kind == "user":
        if user_id is None:
            return [], 0
        params["id"] = user_id
    ok, data, _m = main_api("GET", path, params=params)
    if not ok or data is None:
        return [], 0
    if isinstance(data, list):  # follow 流返回数组
        return data, len(data)
    return data.get("records") or [], data.get("total") or 0


def blog_detail(blog_id: int) -> dict | None:
    ok, data, _m = main_api("GET", f"/api/user/blog/query/{blog_id}")
    return data


def blog_like(blog_id: int) -> tuple[bool, str]:
    ok, _d, msg = main_api("PUT", f"/api/user/blog/like/{blog_id}")
    return ok, msg or ""


def blog_delete(blog_id: int) -> tuple[bool, str]:
    ok, _d, msg = main_api("DELETE", f"/api/user/blog/delete/{blog_id}")
    return ok, msg or ("删除成功" if ok else "删除失败")


def blog_update(blog_id: int, title: str) -> tuple[bool, str]:
    ok, _d, msg = main_api("PUT", "/api/user/blog/update", json_body={"id": blog_id, "title": title})
    return ok, msg or ("修改成功" if ok else "修改失败")


def comments_list(blog_id: int, page_num: int = 1, page_size: int = 50) -> tuple[list[dict], int]:
    ok, data, _m = main_api(
        "GET",
        "/api/user/blog/comments/list",
        params={"blogId": blog_id, "pageNum": page_num, "pageSize": page_size},
    )
    if not ok or not isinstance(data, dict):
        return [], 0
    return data.get("list") or [], data.get("total") or 0


def comment_add(blog_id: int, content: str, parent_id: int = 0) -> tuple[bool, str]:
    ok, _d, msg = main_api(
        "POST",
        "/api/user/blog/comments/add",
        json_body={"blogId": blog_id, "content": content, "parentId": parent_id},
    )
    return ok, msg or ("评论成功" if ok else "评论失败")


def comment_like(comment_id: int) -> tuple[bool, str]:
    ok, _d, msg = main_api("POST", f"/api/user/blog/comments/like/{comment_id}")
    return ok, msg or ""


def comment_delete(comment_id: int) -> tuple[bool, str]:
    ok, _d, msg = main_api("DELETE", f"/api/user/blog/comments/delete/{comment_id}")
    return ok, msg or ("删除成功" if ok else "删除失败")


def follow_user(user_id: int, is_follow: bool) -> tuple[bool, str]:
    ok, _d, msg = main_api("PUT", f"/api/user/follow/{user_id}/{str(is_follow).lower()}")
    return ok, msg or ("操作成功" if ok else "操作失败")


def follow_or_not(user_id: int) -> bool:
    ok, data, _m = main_api("GET", f"/api/user/follow/or/not/{user_id}")
    return bool(data)


# ---------------- AI 投顾（8091） ----------------

def agent_config_list() -> list[dict]:
    ok, data, _i = agent_api("GET", "/api/v1/query_ai_agent_config_list")
    return data or []


def agent_session(agent_id: str, user_id: int) -> str | None:
    ok, data, _i = agent_api(
        "POST", "/api/v1/create_session", json_body={"agentId": agent_id, "userId": str(user_id)}
    )
    if ok and isinstance(data, dict):
        return data.get("sessionId")
    return None


def agent_chat(agent_id: str, user_id: int, session_id: str, message: str) -> tuple[bool, str]:
    """阻塞式对话；LLM 含工具往返可达数十秒，读超时放宽到 180s（对齐服务端预算）。"""
    ok, data, info = agent_api(
        "POST",
        "/api/v1/chat",
        json_body={
            "agentId": agent_id,
            "userId": str(user_id),
            "sessionId": session_id,
            "message": message,
        },
        timeout=httpx.Timeout(180.0, connect=10.0),
    )
    if ok and isinstance(data, dict):
        return True, data.get("content") or ""
    return False, info or "智能体暂不可用"


def agent_trace(agent_id: str, user_id: int | str, session_id: str) -> list[dict]:
    """会话执行轨迹（8091 扩展接口）：[{seq,ts,type,agent,name,args,result,durationMs}, ...]。"""
    ok, data, _i = agent_api(
        "GET", "/api/v1/trace",
        params={"agentId": agent_id, "userId": str(user_id), "sessionId": session_id},
    )
    return data or []


def agent_team(agent_id: str) -> dict | None:
    """智能体团队结构（8091 扩展接口）：{supervisor, experts, tools}；不可用时 None（前端降级隐藏）。"""
    ok, data, _i = agent_api("GET", "/api/v1/agent_team", params={"agentId": agent_id})
    return data if ok else None


# ---------------- AI 投顾扩展：历史会话（MySQL 持久化，原 Java 无） ----------------

def agent_history_list(user_id: int | str) -> list[dict]:
    """历史会话列表 [{sessionId, agentId, title, updateTime}]（最近活跃倒序）。"""
    ok, data, _i = agent_api("GET", "/api/v1/history_list", params={"userId": str(user_id)})
    return data or []


def agent_history_messages(session_id: str) -> list[dict]:
    """历史会话消息 [{role, content, createTime}]（assistant 附 trace）。"""
    ok, data, _i = agent_api("GET", "/api/v1/history_messages", params={"sessionId": session_id})
    return data or []


def agent_history_delete(session_id: str, user_id: int | str) -> bool:
    """删除历史会话（按归属校验）。"""
    ok, _d, _i = agent_api("DELETE", "/api/v1/history_session",
                           params={"sessionId": session_id, "userId": str(user_id)})
    return ok


# ---------------- AI 投顾扩展：个人知识库（MySQL 持久化，原 Java 无） ----------------

def agent_kb_list(user_id: int | str) -> list[dict]:
    """知识库文档列表 [{id, title, charCount, createTime}]。"""
    ok, data, _i = agent_api("GET", "/api/v1/kb_list", params={"userId": str(user_id)})
    return data or []


def agent_kb_upload(user_id: int | str, filename: str, payload: bytes) -> tuple[bool, str]:
    """上传纯文本文档（txt/md ≤512KB）。"""
    try:
        r = http().post(f"{AGENT}/api/v1/kb_upload", data={"userId": str(user_id)},
                        files={"file": (filename, payload)}, timeout=20)
        body = r.json()
    except httpx.HTTPError as e:
        return False, f"知识库上传失败（{e.__class__.__name__}），请确认 8091 已启动"
    if body.get("code") == "0000" and isinstance(body.get("data"), dict):
        return True, f"已收录《{body['data'].get('title', filename)}》"
    return False, body.get("info") or "上传失败"


def agent_kb_delete(doc_id: int, user_id: int | str) -> bool:
    """删除知识库文档（逻辑删除，按归属校验）。"""
    ok, _d, _i = agent_api("DELETE", "/api/v1/kb_doc",
                           params={"docId": doc_id, "userId": str(user_id)})
    return ok


# ---------------- 管理端（userType=3） ----------------

def admin_user_page(params: dict) -> tuple[list[dict], int]:
    ok, data, _m = main_api("GET", "/api/admin/user", params=params)
    if not ok or not isinstance(data, dict):
        return [], 0
    return data.get("list") or [], data.get("total") or 0   # /admin/user 独有 {list,total}


def admin_page(path: str, params: dict) -> tuple[list[dict], int]:
    """其余管理端分页统一为 Page{records,total}。"""
    ok, data, _m = main_api("GET", path, params=params)
    if not ok or not isinstance(data, dict):
        return [], 0
    return data.get("records") or [], data.get("total") or 0


def admin_change_status(user_id: int, status: int) -> tuple[bool, str]:
    ok, _d, msg = main_api("POST", f"/api/admin/user/changeStatus/{user_id}", params={"status": status})
    return ok, msg or "操作失败"


def admin_delete(path: str) -> tuple[bool, str]:
    ok, _d, msg = main_api("DELETE", path)
    return ok, msg or ("删除成功" if ok else "删除失败")


def admin_user_add(body: dict) -> tuple[bool, str]:
    ok, _d, msg = main_api("POST", "/api/admin/user/add", json_body=body)
    return ok, msg or ("新增成功" if ok else "新增失败")


def admin_stock_update(body: dict) -> tuple[bool, str]:
    ok, _d, msg = main_api("PUT", "/api/admin/stock/update", json_body=body)
    return ok, msg or ("修改成功" if ok else "修改失败")
