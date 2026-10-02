"""契约自测：auth.js（登录/注册/登出）+ 拦截器鉴权语义（401/403/放行清单）。

对应前端 lghj_web/src/api/auth.js 与 utils/request.js（token 请求头）。
"""

from __future__ import annotations

import httpx

from conftest import MAIN, assert_result_ok


# ====================== 注册/登录/登出 ======================

def test_register_then_login_full_flow(client: httpx.Client, make_user, suffix: str):
    """注册→登录：响应体结构与字段名（Login.vue 消费 token/id/username/userType/identityDesc/state）。"""
    user = make_user("auth")
    assert isinstance(user["token"], str) and len(user["token"]) > 20
    assert user["userType"] == 1  # 新注册为普通用户
    assert user["identityDesc"] == "普通用户"
    assert user["state"] == 1
    assert user["id"] > 0

    # 再次登录（登录可重复）
    r = client.post(f"{MAIN}/api/login",
                    json={"username": user["username"], "password": user["password"]})
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    assert body["data"]["token"]
    assert body["data"]["id"] == user["id"]


def test_login_wrong_password(client: httpx.Client):
    """错误密码：业务失败（code != 200，HTTP 200），有错误 msg。"""
    r = client.post(f"{MAIN}/api/login", json={"username": "admin", "password": "definitely-wrong"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] != 200
    assert isinstance(body["msg"], str) and body["msg"]


def test_login_nonexistent_user(client: httpx.Client):
    """不存在用户：业务失败。"""
    r = client.post(f"{MAIN}/api/login", json={"username": "no_such_user_f7", "password": "x"})
    assert r.status_code == 200
    assert r.json()["code"] != 200


def test_register_duplicate_username(client: httpx.Client, make_user):
    """重复注册：业务失败（code != 200）。"""
    user = make_user("dup")
    r = client.post(f"{MAIN}/api/register",
                    json={"username": user["username"], "password": "Another123"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] != 200, f"重复注册应失败: {body}"


def test_logout(client: httpx.Client, user_a: dict):
    """登出：POST /api/logout 返回成功（原系统登出不做服务端 token 吊销）。"""
    r = client.post(f"{MAIN}/api/logout", headers=user_a["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())


def test_register_with_optional_fields(client: httpx.Client, suffix: str):
    """注册可选字段（nickName/email/phone，Login.vue 传 undefined 时省略）。"""
    username = f"f7_{suffix}_optreg"
    r = client.post(f"{MAIN}/api/register", json={
        "username": username, "password": "Pass1234",
        "nickName": "联调昵称", "email": "f7@test.local", "phone": "13800000000",
    })
    assert r.status_code == 200
    assert_result_ok(r.json())
    # 登录验证可用
    r = client.post(f"{MAIN}/api/login", json={"username": username, "password": "Pass1234"})
    assert r.json()["code"] == 200


# ====================== 拦截器鉴权语义 ======================

def test_user_endpoint_without_token_401(client: httpx.Client):
    """无 token 访问 /api/user/** → HTTP 401 + Result{code:401, msg:'未登录，无法访问'}。"""
    r = client.get(f"{MAIN}/api/user/account/query_info")
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == 401
    assert "未登录" in body["msg"]


def test_user_endpoint_with_garbage_token_401(client: httpx.Client):
    """伪造 token 访问 /api/user/** → HTTP 401。"""
    r = client.get(f"{MAIN}/api/user/account/query_info", headers={"token": "forged.token.value"})
    assert r.status_code == 401


def test_admin_endpoint_without_token_401(client: httpx.Client):
    """无 token 访问 /api/admin/** → HTTP 401。"""
    r = client.get(f"{MAIN}/api/admin/user")
    assert r.status_code == 401
    assert r.json()["code"] == 401


def test_admin_endpoint_with_normal_user_403(client: httpx.Client, user_a: dict):
    """普通用户 token 访问管理端 → HTTP 403 + code 20012（无管理员权限）。"""
    r = client.get(f"{MAIN}/api/admin/user", headers=user_a["headers"])
    assert r.status_code == 403
    body = r.json()
    assert body["code"] == 20012
    assert "无管理员权限" in body["msg"]


def test_whitelist_anonymous_paths(client: httpx.Client):
    """放行清单（无需 token 可访问）：search/stock_data/quote/news/hot/of/user/comments/list。"""
    for path in [
        "/api/user/stock/search?keyword=600519",
        "/api/user/stock/data?symbol=600519&period=D",
        "/api/user/realtime/quote?market=sh&code=600519",
        "/api/user/realtime/news?symbol=600519",
        "/api/user/blog/query/hot?current=1&size=1",
        "/api/user/blog/query/of/user?id=1&current=1&size=1",
        "/api/user/blog/comments/list?blogId=1",
    ]:
        r = client.get(f"{MAIN}{path}")
        assert r.status_code == 200, f"放行路径应匿名可访问: {path} → {r.status_code}"
        assert r.json()["code"] == 200, f"放行路径业务应成功: {path} → {r.text[:200]}"


def test_non_whitelisted_user_path_still_401(client: httpx.Client):
    """放行清单之外的 /api/user/** 仍需 token（如 /api/user/blog/query/of/me）。"""
    r = client.get(f"{MAIN}/api/user/blog/query/of/me")
    assert r.status_code == 401


def test_internal_api_not_jwt_intercepted(client: httpx.Client):
    """/api/internal/** 不走 JWT 拦截器（控制器自行校验 X-Internal-Token）——
    无 JWT 头但带正确 internal token 时应放行（业务码 200）。"""
    from conftest import INTERNAL_TOKEN
    r = client.get(f"{MAIN}/api/internal/market/realtime",
                   params={"code": "600519", "includeMinute": "false"},
                   headers={"X-Internal-Token": INTERNAL_TOKEN})
    assert r.status_code == 200
    assert r.json()["code"] == 200
