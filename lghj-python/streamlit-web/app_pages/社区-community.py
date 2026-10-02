# -*- coding: utf-8 -*-
"""社区页 —— 博客（热门/我的/关注流/按用户）+ 点赞 + 二级评论 + 关注"""

import streamlit as st

import api

st.header("投资社区", icon=":material/forum:")

logged_in = bool(st.session_state.get("token"))
me = (st.session_state.get("user") or {}).get("id")

tab_hot, tab_me, tab_feed, tab_user = st.tabs(
    ["热门", "我的", "关注流", "TA 的博客"], on_change="rerun"
)


# ---------------- 发布（登录后） ----------------

def publish_form() -> None:
    with st.expander(":material/edit_note: 发布新博客"):
        with st.form("blog_form", border=False):
            title = st.text_input("标题", key="blog_title", max_chars=100)
            context = st.text_area("正文", key="blog_context", height=120, placeholder="分享你的观点、持仓心得…（字段名 context 为原系统契约）")
            if st.form_submit_button("发布", type="primary", icon=":material/send:"):
                if not title.strip() or not context.strip():
                    st.warning("标题和正文不能为空")
                else:
                    ok, msg = api.blog_publish(title.strip(), context.strip())
                    (st.toast if ok else st.error)(msg, icon=":material/check_circle:" if ok else None)
                    st.rerun()


def blog_card(b: dict) -> None:
    """单条博客卡片：标题 / 作者 / 时间 / 点赞 / 评论。"""
    blog_id = b.get("id")
    with st.container(border=True):
        head = st.container(horizontal=True, horizontal_alignment="left")
        st.markdown(
            f"**{b.get('title', '')}**　"
            f"<span style='color:#8B949E;font-size:12px'>{b.get('name', '匿名')} · "
            f"{b.get('createTime', '')}</span>",
            unsafe_allow_html=True,
        )
        content = b.get("context") or b.get("content") or ""
        if content:
            st.caption(content[:160] + ("…" if len(content) > 160 else ""))
        acts = st.container(horizontal=True, horizontal_alignment="left")
        liked = int(b.get("liked") or 0)
        if acts.button(f"❤ {liked}", key=f"like_{blog_id}", disabled=not logged_in):
            ok, msg = api.blog_like(blog_id)
            if ok:
                st.toast("已点赞", icon=":material/favorite:")
                st.rerun()
        if logged_in and b.get("userId") == me:
            if acts.button("删除", key=f"del_{blog_id}", icon=":material/delete:"):
                ok, msg = api.blog_delete(blog_id)
                (st.toast if ok else st.error)(msg, icon=":material/check_circle:" if ok else None)
                st.rerun()
        if logged_in and b.get("userId") not in (None, me):
            following = st.session_state.get(f"follow_{b.get('userId')}")
            if following is None:
                following = api.follow_or_not(b.get("userId"))
                st.session_state[f"follow_{b.get('userId')}"] = following
            btn = "已关注 ✓" if following else "+ 关注作者"
            if acts.button(btn, key=f"follow_{blog_id}"):
                ok, msg = api.follow_user(b.get("userId"), not following)
                if ok:
                    st.session_state[f"follow_{b.get('userId')}"] = not following
                    st.rerun()

        comments_area(blog_id)


def comments_area(blog_id: int) -> None:
    """评论树（二级）+ 发评论。"""
    with st.expander(f"💬 评论 ({st.session_state.get(f'cmt_total_{blog_id}', '…')})"):
        items, total = api.comments_list(blog_id)
        st.session_state[f"cmt_total_{blog_id}"] = total

        def render_comment(c: dict, depth: int = 0) -> None:
            u = c.get("user") or {}
            with st.container(border=depth > 0):
                st.markdown(
                    f"{'　' * depth}**{u.get('nickname') or u.get('id', '游客')}**　"
                    f"<span style='color:#8B949E;font-size:11px'>{c.get('liked') or 0} 赞</span>",
                    unsafe_allow_html=True,
                )
                st.caption(c.get("content", ""))
                row = st.container(horizontal=True, horizontal_alignment="left")
                if row.button("👍", key=f"cl_{c.get('id')}", disabled=not logged_in):
                    ok, _m = api.comment_like(c.get("id"))
                    if ok:
                        st.rerun()
                if logged_in and c.get("userId") == me:
                    if row.button("删除", key=f"cd_{c.get('id')}"):
                        ok, _m = api.comment_delete(c.get("id"))
                        if ok:
                            st.rerun()
                if row.button("回复", key=f"cr_{c.get('id')}"):
                    st.session_state[f"reply_parent_{blog_id}"] = c.get("id")
                if st.session_state.get(f"reply_parent_{blog_id}") == c.get("id"):
                    with st.form(f"reply_form_{c.get('id')}", border=False):
                        txt = st.text_input("回复内容", key=f"reply_txt_{c.get('id')}")
                        if st.form_submit_button("发送", type="primary"):
                            if txt.strip():
                                ok, _m = api.comment_add(blog_id, txt.strip(), c.get("id") or 0)
                                if ok:
                                    st.session_state.pop(f"reply_parent_{blog_id}", None)
                                    st.rerun()
                for child in c.get("children") or []:
                    render_comment(child, depth + 1)

        if not items:
            st.caption("暂无评论")
        for c in items:
            render_comment(c)

        if logged_in:
            with st.form(f"cmt_form_{blog_id}", border=False):
                txt = st.text_input("写评论…", key=f"cmt_txt_{blog_id}")
                if st.form_submit_button("评论", type="primary"):
                    if txt.strip():
                        ok, _m = api.comment_add(blog_id, txt.strip(), 0)
                        if ok:
                            st.rerun()


def pager(key: str, current: int, total: int, size: int) -> int | None:
    """简单翻页，返回新的页码或 None。"""
    pages = max(1, -(-total // size))
    if pages <= 1:
        return None
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.caption(f"第 {current} / {pages} 页 · 共 {total} 条")
    if c1.button("上一页", key=f"prev_{key}", disabled=current <= 1):
        return current - 1
    if c3.button("下一页", key=f"next_{key}", disabled=current >= pages):
        return current + 1
    return None


def render_list(kind: str) -> None:
    current = st.session_state.get(f"page_{kind}", 1)
    size = 10
    records, total = api.blog_page(kind, current, size)
    if not records:
        st.caption("这里还没有内容")
        return
    for b in records:
        blog_card(b)
    if (np := pager(kind, current, total, size)) is not None:
        st.session_state[f"page_{kind}"] = np
        st.rerun()


if tab_hot.open:
    render_list("hot")

if tab_me.open:
    if not logged_in:
        st.info("「我的博客」需要登录")
        st.page_link("app_pages/登录-login.py", label="去登录 / 注册 →", icon=":material/login:")
    else:
        publish_form()
        render_list("me")

if tab_feed.open:
    if not logged_in:
        st.info("关注流需要登录（Redis 收件箱推送）")
        st.page_link("app_pages/登录-login.py", label="去登录 / 注册 →", icon=":material/login:")
    else:
        render_list("follow")

if tab_user.open:
    with st.form("user_blog_form", border=False):
        uid = st.number_input("用户 ID", min_value=1, step=1, key="query_user_id")
        if st.form_submit_button("查询", type="primary", icon=":material/search:"):
            st.session_state.user_blog_target = int(uid)
    if st.session_state.get("user_blog_target"):
        st.session_state.setdefault("page_user", 1)
        records, total = api.blog_page("user", st.session_state.page_user, 10, st.session_state.user_blog_target)
        if not records:
            st.caption("该用户暂无博客")
        for b in records:
            blog_card(b)
        if (np := pager("user", st.session_state.page_user, total, 10)) is not None:
            st.session_state.page_user = np
            st.rerun()
