"""契约自测：admin.js（管理端用户/交易/博客/评论/股票管理）。

重点：/admin/user 为 PageResult{list,total}，其余管理端分页为 Page{records,total,size,current,pages}；
VO 无 id 字段、枚举转中文名；用户增/改/启禁/删全流程。
"""

from __future__ import annotations

import httpx

from conftest import MAIN, assert_result_ok


# ====================== 用户管理（PageResult{list,total}） ======================

def test_user_page_uses_list_total(client: httpx.Client, admin: dict):
    """GET /api/admin/user：data 为 {list,total}（前端 UserManage.vue 唯一消费 .list 的接口）。"""
    r = client.get(f"{MAIN}/api/admin/user", params={"current": 1, "size": 5},
                   headers=admin["headers"])
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    page = body["data"]
    assert "list" in page and "total" in page, f"/admin/user 应为 PageResult{{list,total}}: {page}"
    assert page["total"] >= 1
    assert isinstance(page["list"], list) and page["list"]
    vo = page["list"][0]
    # UserVO 契约：无 id 字段；sex/userType/status 为中文名；createUser 字符串
    assert "id" not in vo, f"UserVO 不应含 id 字段: {vo}"
    for field in ("username", "email", "phone", "sex", "userType", "status", "createTime"):
        assert field in vo, f"UserVO 缺字段 {field}: {vo}"
    assert vo["userType"] == "管理员" or isinstance(vo["userType"], str)
    assert vo["status"] in ("正常", "禁用")
    # sex 枚举转中文名（0/未知 → "未知状态"，原 Sex2Num 枚举语义）
    assert vo["sex"] in ("男", "女", "未知状态", None)


def test_user_add_update_changestatus_delete(client: httpx.Client, admin: dict, suffix: str,
                                             db_conn):
    """新增→按用户名查→改→启用/禁用→删（逻辑删除），全流程。"""
    username = f"f7admf_{suffix}"
    # 新增（UserDTO：username/password/userType 必填）
    r = client.post(f"{MAIN}/api/admin/user/add",
                    json={"username": username, "password": "Pass1234", "userType": 1,
                          "nickName": "联调管理新增", "email": "f7adm@test.local"},
                    headers=admin["headers"])
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)

    # 条件查询定位
    r = client.get(f"{MAIN}/api/admin/user",
                   params={"current": 1, "size": 10, "username": username},
                   headers=admin["headers"])
    page = r.json()["data"]
    assert page["total"] == 1, f"按用户名条件查询应命中 1 条: {page}"
    # UserVO 无 id → 通过 DB 取 id（只读查询）
    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM user WHERE username=%s AND is_deleted=0", (username,))
        row = cur.fetchone()
    assert row, "新增用户应落库"
    user_id = row[0]

    # 修改（email；UserVO 契约无 nickName 字段，昵称改动以 DB 为准，见下）
    r = client.put(f"{MAIN}/api/admin/user/update",
                   json={"id": user_id, "email": "f7adm-updated@test.local",
                         "nickName": "联调已修改"},
                   headers=admin["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())
    r = client.get(f"{MAIN}/api/admin/user/{user_id}", headers=admin["headers"])
    vo = r.json()["data"]
    assert vo["email"] == "f7adm-updated@test.local", f"修改未生效: {vo}"
    with db_conn.cursor() as cur:
        cur.execute("SELECT nick_name FROM user WHERE id=%s", (user_id,))
        assert cur.fetchone()[0] == "联调已修改", "昵称修改应落库"

    # 启用/禁用（query 传 status；msg 文案契约）
    r = client.post(f"{MAIN}/api/admin/user/changeStatus/{user_id}", params={"status": 0},
                    headers=admin["headers"])
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    assert body["msg"] == "禁用账号成功", f"禁用文案契约: {body}"
    r = client.post(f"{MAIN}/api/admin/user/changeStatus/{user_id}", params={"status": 1},
                    headers=admin["headers"])
    assert r.json()["msg"] == "启用账号成功"

    # 删除（逻辑删除）
    r = client.delete(f"{MAIN}/api/admin/user/{user_id}", headers=admin["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())
    # 再查详情：逻辑删除后查不到 → data null（列表 total 归零）
    r = client.get(f"{MAIN}/api/admin/user/{user_id}", headers=admin["headers"])
    assert r.json()["data"] is None, f"逻辑删除后详情应为 null: {r.json()}"


def test_user_add_duplicate_username_fails(client: httpx.Client, admin: dict, suffix: str):
    """新增重复用户名：首次成功、再次新增 code=500（SYSTEM_ERROR，原 RuntimeException 语义）。"""
    username = f"f7admdup_{suffix}"
    r = client.post(f"{MAIN}/api/admin/user/add",
                    json={"username": username, "password": "Pass1234", "userType": 1},
                    headers=admin["headers"])
    assert_result_ok(r.json())
    r = client.post(f"{MAIN}/api/admin/user/add",
                    json={"username": username, "password": "Pass1234", "userType": 1},
                    headers=admin["headers"])
    assert r.json()["code"] == 500, f"重复用户名应失败: {r.json()}"


# ====================== 交易管理（Page{records,total,...}） ======================

def test_trade_order_page_structure(client: httpx.Client, admin: dict):
    """GET /api/admin/trade/order/page：Page 结构 records/total/size/current/pages。"""
    r = client.get(f"{MAIN}/api/admin/trade/order/page",
                   params={"pageNum": 1, "pageSize": 5}, headers=admin["headers"])
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    page = body["data"]
    for field in ("records", "total", "size", "current", "pages"):
        assert field in page, f"交易订单分页应为 MP Page 结构，缺 {field}: {page}"
    assert isinstance(page["records"], list)
    if page["records"]:
        order = page["records"][0]
        for field in ("id", "userId", "symbol", "direction", "price", "quantity", "status"):
            assert field in order, f"订单记录缺字段 {field}: {order}"


def test_trade_deal_page_and_filter(client: httpx.Client, admin: dict, trader_user: dict):
    """GET /api/admin/trade/deal/page：Page 结构 + userId 过滤。"""
    r = client.get(f"{MAIN}/api/admin/trade/deal/page",
                   params={"pageNum": 1, "pageSize": 5, "userId": trader_user["id"]},
                   headers=admin["headers"])
    assert r.status_code == 200
    page = r.json()["data"]
    for field in ("records", "total", "size", "current", "pages"):
        assert field in page, f"成交分页缺 {field}: {page}"
    for deal in page["records"]:
        assert deal["userId"] == trader_user["id"], f"userId 过滤失效: {deal}"


# ====================== 博客/评论管理 ======================

def test_blog_page_structure(client: httpx.Client, admin: dict):
    """GET /api/admin/blog/page：Page{records,total}。"""
    r = client.get(f"{MAIN}/api/admin/blog/page", params={"pageNum": 1, "pageSize": 5},
                   headers=admin["headers"])
    assert r.status_code == 200
    page = r.json()["data"]
    assert "records" in page and "total" in page, f"博客分页应为 Page 结构: {page}"
    if page["records"]:
        blog = page["records"][0]
        for field in ("id", "title", "context", "userId", "createTime"):
            assert field in blog, f"博客记录缺字段 {field}: {blog}"


def test_comments_page_structure(client: httpx.Client, admin: dict):
    """GET /api/admin/blog/comments/page：Page 结构，create_time 倒序。"""
    r = client.get(f"{MAIN}/api/admin/blog/comments/page",
                   params={"pageNum": 1, "pageSize": 5}, headers=admin["headers"])
    assert r.status_code == 200
    page = r.json()["data"]
    assert "records" in page and "total" in page


def test_admin_blog_detail_and_delete(client: httpx.Client, admin: dict, user_a: dict,
                                      suffix: str, db_conn):
    """管理端博客详情 GET /{id} 与删除 DELETE /{id}（逻辑删除）。"""
    title = f"f7adm博客_{suffix}"
    r = client.post(f"{MAIN}/api/user/blog", json={"title": title, "context": "管理端删除测试"},
                    headers=user_a["headers"])
    assert_result_ok(r.json())
    # 找到 id（DB 只读）
    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM blog WHERE title=%s AND is_deleted=0 ORDER BY id DESC", (title,))
        row = cur.fetchone()
    assert row
    blog_id = row[0]

    r = client.get(f"{MAIN}/api/admin/blog/{blog_id}", headers=admin["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())
    assert r.json()["data"]["title"] == title

    r = client.delete(f"{MAIN}/api/admin/blog/{blog_id}", headers=admin["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())


# ====================== 股票管理 ======================

def test_stock_page_structure(client: httpx.Client, admin: dict):
    """GET /api/admin/stock/page：Page 结构 + keyword 过滤（StockManage.vue 消费 records）。"""
    r = client.get(f"{MAIN}/api/admin/stock/page",
                   params={"pageNum": 1, "pageSize": 3, "keyword": "600519"},
                   headers=admin["headers"])
    assert r.status_code == 200
    page = r.json()["data"]
    for field in ("records", "total", "size", "current", "pages"):
        assert field in page, f"股票分页缺 {field}: {page}"
    assert page["total"] >= 1
    stock = page["records"][0]
    assert stock["symbol"] == "600519"
    assert "name" in stock and "industry" in stock


def test_stock_update_idempotent(client: httpx.Client, admin: dict):
    """PUT /api/admin/stock/update：按 symbol 更新（用原名回写，幂等不改数据）。"""
    # 取当前行业值
    r = client.get(f"{MAIN}/api/admin/stock/page",
                   params={"pageNum": 1, "pageSize": 1, "keyword": "600519"},
                   headers=admin["headers"])
    stock = r.json()["data"]["records"][0]
    r = client.put(f"{MAIN}/api/admin/stock/update",
                   json={"symbol": "600519", "industry": stock["industry"]},
                   headers=admin["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())


def test_stock_sync_es_and_init_es(client: httpx.Client, admin: dict):
    """sync-es（需管理员 token）/init-es（放行）：ES 占位契约，文案在 msg。"""
    r = client.post(f"{MAIN}/api/admin/stock/sync-es", headers=admin["headers"])
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    assert body["msg"] == "同步完成"

    r = client.post(f"{MAIN}/api/admin/stock/init-es")  # 拦截器放行，无需 token
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    assert "ES 初始化完成" in body["msg"] and "5458" in body["msg"], f"init-es 文案契约: {body}"
