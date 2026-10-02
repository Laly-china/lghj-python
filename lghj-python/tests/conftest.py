"""Phase 7 三服务联调 pytest 契约自测 - 公共夹具（conftest）。

依赖运行中的三服务：
- lghj-server      http://127.0.0.1:8080（主服务，Result{code,msg,data}，成功码 200）
- ai-agent-server  http://127.0.0.1:8091（智能体，Response{code,info,data}，成功码 "0000"）
- prediction-server http://127.0.0.1:8001（预测，裸 JSON）

可重复执行约定：
- 每次运行生成随机用户名后缀（uuid），互不冲突；
- 注册的测试用户在夹具 teardown 经管理端 API 逻辑删除（自清理）；
- 博客/评论/自选股等测试数据经业务 API 删除（自清理）；
- 不 DROP 表、不清库、不重复导入股票。
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

MAIN = "http://127.0.0.1:8080"
AGENT = "http://127.0.0.1:8091"
PRED = "http://127.0.0.1:8001"

# 与启动服务时设置的 LGHJ_INTERNAL_API_TOKEN 一致（internal API 鉴权）
INTERNAL_TOKEN = "phase7-internal-token"

# 已知管理员账号（任务B 自测留下的演示数据；只读使用，绝不删除）
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "123456"

TIMEOUT = httpx.Timeout(30.0, read=300.0)  # agent chat（LLM 真调）给长读超时


# ====================== 公共工具 ======================

def make_suffix() -> str:
    """随机后缀（每次运行唯一，保证测试可重复执行）。"""
    return uuid.uuid4().hex[:10]


def register_and_login(client: httpx.Client, username: str, password: str = "Pass1234") -> dict:
    """注册并登录，返回登录 data（含 token/id/username/userType...）。"""
    r = client.post(f"{MAIN}/api/register", json={"username": username, "password": password})
    assert r.status_code == 200, f"注册失败: {r.text}"
    r = client.post(f"{MAIN}/api/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败: {r.text}"
    body = r.json()
    assert body["code"] == 200, f"登录业务失败: {body}"
    assert body["data"] and body["data"]["token"], f"登录未返回 token: {body}"
    return body["data"]


# ====================== 夹具 ======================

@pytest.fixture(scope="session")
def suffix() -> str:
    return make_suffix()


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(timeout=TIMEOUT) as c:
        yield c


@pytest.fixture(scope="session")
def admin(client: httpx.Client) -> dict:
    """管理员会话（userType=3），headers 含 admin token。"""
    data = register_and_login(client, ADMIN_USERNAME, ADMIN_PASSWORD)
    assert data["userType"] == 3, "admin 账号必须为管理员（userType=3）"
    return {**data, "headers": {"token": data["token"]}}


@pytest.fixture(scope="session")
def make_user(client: httpx.Client, admin: dict, suffix: str):
    """用户工厂：注册+登录随机用户，返回 {id, username, password, token, headers}。

    teardown：经管理端 DELETE /api/admin/user/{id} 逻辑删除（自清理，admin 本尊除外）。
    """
    created: list[dict] = []

    def _make(tag: str = "u", password: str = "Pass1234") -> dict:
        username = f"f7_{suffix}_{tag}_{len(created)}"
        data = register_and_login(client, username, password)
        user = {**data, "username": username, "password": password,
                "headers": {"token": data["token"]}}
        created.append(user)
        return user

    yield _make

    # 自清理：先删用户产生的业务数据（博客/自选股），再逻辑删除用户。
    # 注意：注册用户无 user_role 关联行，管理端删除会 500（原 MyBatis-Plus remove()
    # 0 行返回 false → 原系统同样报"用户-角色关联记录删除失败"，忠实行为），
    # 但用户行已先行逻辑删除，清理目的达成。
    for user in created:
        try:
            blogs = client.get(f"{MAIN}/api/user/blog/query/of/me",
                               params={"current": 1, "size": 50},
                               headers=user["headers"]).json()["data"] or []
            for blog in blogs:
                client.delete(f"{MAIN}/api/user/blog/delete/{blog['id']}",
                              headers=user["headers"])
            opts = client.get(f"{MAIN}/api/user/optional/list",
                              headers=user["headers"]).json()["data"] or []
            for opt in opts:
                client.post(f"{MAIN}/api/user/optional/remove",
                            params={"symbol": opt["symbol"]}, headers=user["headers"])
        except Exception:  # noqa: BLE001 业务清理失败不阻断
            pass
        client.delete(f"{MAIN}/api/admin/user/{user['id']}", headers=admin["headers"])


@pytest.fixture(scope="session")
def user_a(make_user) -> dict:
    return make_user("a")


@pytest.fixture(scope="session")
def user_b(make_user) -> dict:
    return make_user("b")


@pytest.fixture(scope="session")
def db_conn():
    """直连 MySQL（只做只读校验与测试数据核对，绝不 DDL/DROP）。

    autocommit=True：避免 REPEATABLE READ 快照老化导致后续只读查询
    看不见服务端新提交的数据。
    """
    import pymysql

    conn = pymysql.connect(host="127.0.0.1", port=3306, user="root",
                           password="123456", database="lghj", charset="utf8mb4",
                           autocommit=True)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def trader_user(client: httpx.Client, make_user) -> dict:
    """已完成一次买入成交的用户（供管理端交易分页过滤等跨模块测试）。"""
    import time

    quote = client.get(f"{MAIN}/api/user/realtime/quote",
                       params={"market": "sh", "code": "600519"}).json()["data"]
    assert quote and float(quote["price"]) > 0, "现价获取失败"
    user = make_user("tradeuid")
    r = client.post(f"{MAIN}/api/user/account/create", headers=user["headers"])
    assert r.json()["code"] == 200
    price = round(float(quote["price"]) * 1.05, 2)
    r = client.post(f"{MAIN}/api/user/trade/order",
                    params={"symbol": "600519", "direction": 1, "price": price, "quantity": 1},
                    headers=user["headers"])
    assert r.json()["code"] == 200, r.json()
    order_id = r.json()["data"]["id"]
    deadline = time.monotonic() + 12
    status = None
    while time.monotonic() < deadline:
        orders = client.get(f"{MAIN}/api/user/trade/query_orders", headers=user["headers"]).json()["data"]
        status = next((o["status"] for o in orders if o["id"] == order_id), None)
        if status == 3:
            break
        time.sleep(0.5)
    assert status == 3, "trader_user 夹具：买入应成交"
    return user


# ====================== 断言辅助 ======================

def assert_result_ok(body: dict) -> None:
    """主服务 Result 成功断言：{code:200, msg, data}。"""
    assert body.get("code") == 200, f"期望 code=200，实际: {json.dumps(body, ensure_ascii=False)[:300]}"
    assert isinstance(body.get("msg"), str), "Result.msg 应为字符串"
    assert "data" in body, "Result 应含 data 字段"


def assert_response_ok(body: dict) -> None:
    """Agent 服务 Response 成功断言：{code:"0000", info, data}。"""
    assert body.get("code") == "0000", f"期望 code='0000'，实际: {json.dumps(body, ensure_ascii=False)[:300]}"
    assert isinstance(body.get("info"), str), "Response.info 应为字符串"
    assert "data" in body, "Response 应含 data 字段"


def read_log_tail(path: str, from_offset: int) -> str:
    """读取日志文件 from_offset 之后的增量（用于验证跨服务调用确实发生）。"""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(from_offset)
            return f.read()
    except OSError:
        return ""


def log_size(path: str) -> int:
    try:
        import os
        return os.path.getsize(path)
    except OSError:
        return 0
