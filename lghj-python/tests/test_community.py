"""契约自测：community.js + user.js（博客/评论/点赞/关注/Feed 流）。

重点：发布博客 body 字段名为 **context**（community.js 显式改名后发送）；
评论列表为 PageResult{list,total}；Feed 保序；user.js 关注/取关。
"""

from __future__ import annotations

import httpx

from conftest import MAIN, assert_result_ok


def _publish(client: httpx.Client, user: dict, title: str, context: str) -> None:
    """发布博客（body 用 context 字段名——前端 publishBlog 的坑点）。"""
    r = client.post(f"{MAIN}/api/user/blog", json={"title": title, "context": context},
                    headers=user["headers"])
    assert r.status_code == 200, r.text
    assert_result_ok(r.json())


def _my_blogs(client: httpx.Client, user: dict, current: int = 1, size: int = 10) -> list:
    r = client.get(f"{MAIN}/api/user/blog/query/of/me",
                   params={"current": current, "size": size}, headers=user["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())
    return r.json()["data"]


# ====================== 发布与查询 ======================

def test_publish_blog_with_context_field(client: httpx.Client, user_a: dict, suffix: str):
    """发布（context 字段）→ 我的博客列表可见，内容字段为 context。"""
    title = f"f7博客_{suffix}_pub"
    _publish(client, user_a, title, "这是联调测试内容，字段名是 context")
    blogs = _my_blogs(client, user_a)
    assert isinstance(blogs, list)
    hit = next((b for b in blogs if b.get("title") == title), None)
    assert hit is not None, f"发布的博客应在 query/of/me 列表: {[b.get('title') for b in blogs][:5]}"
    for field in ("id", "title", "context", "userId", "createTime", "liked", "comments"):
        assert field in hit, f"博客条目缺字段 {field}: {hit}"
    assert hit["context"] == "这是联调测试内容，字段名是 context"
    user_a["blog_id"] = hit["id"]


def test_blog_detail(client: httpx.Client, user_a: dict, suffix: str):
    """详情：content||context 双兜底的后端字段为 context，含作者昵称与 isLike。"""
    title = f"f7博客_{suffix}_detail"
    _publish(client, user_a, title, "详情校验内容")
    blogs = _my_blogs(client, user_a)
    blog_id = next(b["id"] for b in blogs if b["title"] == title)
    r = client.get(f"{MAIN}/api/user/blog/query/{blog_id}", headers=user_a["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())
    detail = r.json()["data"]
    assert detail["id"] == blog_id
    assert detail["title"] == title
    assert detail["context"] == "详情校验内容"
    assert detail["userId"] == user_a["id"]
    assert detail.get("name") is not None, "详情应补作者昵称"
    assert "isLike" in detail and "liked" in detail


def test_query_blog_of_user_anonymous(client: httpx.Client, user_a: dict, suffix: str):
    """query/of/user 放行（无需登录），id 必传。"""
    title = f"f7博客_{suffix}_ofuser"
    _publish(client, user_a, title, "指定用户查询")
    r = client.get(f"{MAIN}/api/user/blog/query/of/user",
                   params={"id": user_a["id"], "current": 1, "size": 10})
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    assert any(b.get("title") == title for b in body["data"])


def test_hot_blogs_anonymous(client: httpx.Client):
    """query/hot 放行：热度排序分页可匿名访问。"""
    r = client.get(f"{MAIN}/api/user/blog/query/hot", params={"current": 1, "size": 5})
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    assert isinstance(body["data"], list)


# ====================== 点赞 ======================

def test_like_blog_toggle(client: httpx.Client, user_a: dict, user_b: dict, suffix: str):
    """点赞→计数+1；再点赞→取消（toggle 回落）。"""
    title = f"f7博客_{suffix}_like"
    _publish(client, user_a, title, "点赞测试")
    blogs = _my_blogs(client, user_a)
    blog_id = next(b["id"] for b in blogs if b["title"] == title)
    user_a["like_blog_id"] = blog_id

    # B 点赞
    r = client.put(f"{MAIN}/api/user/blog/like/{blog_id}", headers=user_b["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())
    detail = client.get(f"{MAIN}/api/user/blog/query/{blog_id}", headers=user_b["headers"]).json()["data"]
    assert detail["liked"] == 1, f"点赞后计数应为 1: {detail}"
    assert detail["isLike"] is True

    # B 再点赞 → 取消
    r = client.put(f"{MAIN}/api/user/blog/like/{blog_id}", headers=user_b["headers"])
    assert r.status_code == 200
    detail = client.get(f"{MAIN}/api/user/blog/query/{blog_id}", headers=user_b["headers"]).json()["data"]
    assert detail["liked"] == 0, f"取消点赞后计数应为 0: {detail}"
    assert detail["isLike"] is False


# ====================== 评论（一级/二级/点赞/删除） ======================

def test_comment_two_level_tree(client: httpx.Client, user_a: dict, user_b: dict, suffix: str):
    """发评→列表 PageResult{list,total}→二级回复进 children→评论点赞→删除评论。"""
    title = f"f7博客_{suffix}_cmt"
    _publish(client, user_a, title, "评论测试")
    blogs = _my_blogs(client, user_a)
    blog_id = next(b["id"] for b in blogs if b["title"] == title)
    user_a["cmt_blog_id"] = blog_id

    # B 发一级评论（body: blogId/parentId/content）
    r = client.post(f"{MAIN}/api/user/blog/comments/add",
                    json={"blogId": blog_id, "parentId": 0, "content": "一级评论内容"},
                    headers=user_b["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())

    # 评论列表（放行接口，blogId 必传）: PageResult{list,total}
    r = client.get(f"{MAIN}/api/user/blog/comments/list",
                   params={"blogId": blog_id, "pageNum": 1, "pageSize": 10})
    assert r.status_code == 200
    body = r.json()
    assert_result_ok(body)
    page = body["data"]
    assert "list" in page and "total" in page, f"评论列表应为 PageResult{{list,total}}: {page}"
    assert page["total"] >= 1
    first = page["list"][0]
    for field in ("id", "content", "createTime", "liked", "isLiked", "children"):
        assert field in first, f"评论 VO 缺字段 {field}: {first}"
    assert "user" in first and "nickname" in (first["user"] or {})
    comment_id = first["id"]
    user_b["comment_id"] = comment_id

    # A 回复 → 二级评论进 children
    r = client.post(f"{MAIN}/api/user/blog/comments/add",
                    json={"blogId": blog_id, "parentId": comment_id, "content": "二级回复内容"},
                    headers=user_a["headers"])
    assert r.status_code == 200
    r = client.get(f"{MAIN}/api/user/blog/comments/list", params={"blogId": blog_id})
    first = r.json()["data"]["list"][0]
    assert any(c["content"] == "二级回复内容" for c in first["children"]), "二级回复应挂在 children"

    # 评论点赞（A 给 B 的评论点赞）
    r = client.post(f"{MAIN}/api/user/blog/comments/like/{comment_id}", headers=user_a["headers"])
    assert r.status_code == 200
    # comments/list 在拦截器放行清单内：原 Java 不走 preHandle → BaseContext 为空
    # → isLiked 恒为 0（与是否带 token 无关，忠实原语义）；liked 计数反映点赞状态
    r = client.get(f"{MAIN}/api/user/blog/comments/list", params={"blogId": blog_id},
                   headers=user_a["headers"])
    first = r.json()["data"]["list"][0]
    assert int(first["liked"]) == 1, f"评论点赞计数应为 1: {first}"
    assert first["isLiked"] == 0, "放行端点 isLiked 恒为 0（原系统语义）"

    # 删除一级评论
    r = client.delete(f"{MAIN}/api/user/blog/comments/delete/{comment_id}", headers=user_b["headers"])
    assert r.status_code == 200
    r = client.get(f"{MAIN}/api/user/blog/comments/list", params={"blogId": blog_id})
    assert r.json()["data"]["total"] == 0, "删除一级评论后列表应为空"


# ====================== 关注与 Feed 流（保序） ======================

def test_follow_and_feed_order(client: httpx.Client, user_a: dict, user_b: dict, suffix: str):
    """user.js 关注/是否关注 + Feed 流：B 关注 A → A 连发两博 → B 的 Feed 按 zrevrange 保序。"""
    # B 关注 A（PUT /api/user/follow/{id}/{isFollow}）
    r = client.put(f"{MAIN}/api/user/follow/{user_a['id']}/true", headers=user_b["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())
    r = client.get(f"{MAIN}/api/user/follow/or/not/{user_a['id']}", headers=user_b["headers"])
    assert r.status_code == 200
    assert r.json()["data"] is True, "关注后 or/not 应为 true"

    # A 连发两篇（blog2 更晚 → Feed 中应排更前）
    t1 = f"f7feed_{suffix}_第一篇"
    t2 = f"f7feed_{suffix}_第二篇"
    _publish(client, user_a, t1, "feed-1")
    _publish(client, user_a, t2, "feed-2")

    # Feed 流（PageResult{list,total,...}）
    r = client.get(f"{MAIN}/api/user/blog/query/of/follow",
                   params={"current": 1, "size": 10}, headers=user_b["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())
    feed = r.json()["data"]
    assert "list" in feed and "total" in feed, f"Feed 应为 PageResult: {feed}"
    titles = [b["title"] for b in feed["list"]]
    assert t1 in titles and t2 in titles, f"Feed 应含关注者的两篇博客: {titles}"
    i1, i2 = titles.index(t1), titles.index(t2)
    assert i2 < i1, f"Feed 应按时间倒序保序（新在前）: {titles}"

    # 取关 → or/not false
    r = client.put(f"{MAIN}/api/user/follow/{user_a['id']}/false", headers=user_b["headers"])
    assert r.status_code == 200
    r = client.get(f"{MAIN}/api/user/follow/or/not/{user_a['id']}", headers=user_b["headers"])
    assert r.json()["data"] is False


# ====================== 编辑与删除 ======================

def test_update_blog(client: httpx.Client, user_a: dict, suffix: str):
    """编辑博客（PUT update：id/title 生效）。"""
    title = f"f7博客_{suffix}_upd"
    _publish(client, user_a, title, "编辑前内容")
    blogs = _my_blogs(client, user_a)
    blog_id = next(b["id"] for b in blogs if b["title"] == title)
    new_title = title + "_改"
    r = client.put(f"{MAIN}/api/user/blog/update",
                   json={"id": blog_id, "title": new_title}, headers=user_a["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())
    detail = client.get(f"{MAIN}/api/user/blog/query/{blog_id}", headers=user_a["headers"]).json()["data"]
    assert detail["title"] == new_title


def test_delete_blog_and_permission(client: httpx.Client, user_a: dict, user_b: dict, suffix: str):
    """删除自己的博客 OK；删除他人博客 code=30003。"""
    title = f"f7博客_{suffix}_del"
    _publish(client, user_a, title, "删除测试")
    blogs = _my_blogs(client, user_a)
    blog_id = next(b["id"] for b in blogs if b["title"] == title)

    # B 删 A 的 → 30003
    r = client.delete(f"{MAIN}/api/user/blog/delete/{blog_id}", headers=user_b["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 30003, f"删除他人博客应 30003: {body}"

    # A 删自己的 → 成功，详情不可见
    r = client.delete(f"{MAIN}/api/user/blog/delete/{blog_id}", headers=user_a["headers"])
    assert r.status_code == 200
    assert_result_ok(r.json())
    detail = client.get(f"{MAIN}/api/user/blog/query/{blog_id}", headers=user_a["headers"]).json()
    assert detail["code"] == 30002, f"已删除博客详情应 30002 博客不存在: {detail}"
