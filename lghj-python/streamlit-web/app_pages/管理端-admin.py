# -*- coding: utf-8 -*-
"""管理端 —— 用户 / 股票 / 博客 / 评论 / 交易管理（userType=3）"""

import pandas as pd
import streamlit as st

import api

st.header("管理端", icon=":material/admin_panel_settings:")

user = st.session_state.get("user") or {}
if not st.session_state.get("token") or user.get("userType") != 3:
    st.warning("仅管理员（userType=3，如 admin/123456）可访问")
    st.stop()

tab_user, tab_stock, tab_blog, tab_cmt, tab_trade = st.tabs(
    ["用户管理", "股票管理", "博客管理", "评论管理", "交易管理"], on_change="rerun"
)


def admin_pager(key: str, current: int, total: int, size: int) -> int | None:
    pages = max(1, -(-total // size))
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.caption(f"第 {current} / {pages} 页 · 共 {total} 条")
    if c1.button("上一页", key=f"aprev_{key}", disabled=current <= 1):
        return current - 1
    if c3.button("下一页", key=f"anext_{key}", disabled=current >= pages):
        return current + 1
    return None


# ---------------- 用户管理 ----------------

if tab_user.open:
    st.session_state.setdefault("adm_user_page", 1)
    params = {"pageNum": st.session_state.adm_user_page, "pageSize": 10}
    if kw := st.text_input("用户名/昵称筛选", key="adm_user_kw"):
        params["keyword"] = kw
    rows, total = api.admin_user_page(params)
    st.caption("注：原系统 UserVO 不含用户 id（历史契约），本页仅支持查看与新增；启停/删除请经数据库或后续接口扩展")
    if rows:
        df = pd.DataFrame(
            [
                {
                    "username": r.get("username"),
                    "email": r.get("email") or "-",
                    "phone": r.get("phone") or "-",
                    "sex": r.get("sex") or "-",
                    "userType": r.get("userType"),
                    "status": r.get("status"),
                    "createTime": r.get("createTime"),
                }
                for r in rows
            ]
        )
        st.dataframe(df, hide_index=True, width="stretch")
    else:
        st.caption("无匹配用户")
    if (np := admin_pager("user", st.session_state.adm_user_page, total, 10)) is not None:
        st.session_state.adm_user_page = np
        st.rerun()

    with st.expander(":material/person_add: 新增用户"):
        with st.form("adm_user_add", border=False):
            c1, c2 = st.columns(2)
            uname = c1.text_input("用户名", key="adm_uname")
            pwd = c2.text_input("密码", key="adm_upwd")
            c3, c4 = st.columns(2)
            nick = c3.text_input("昵称", key="adm_unick")
            utype = c4.selectbox("用户类型", ["1", "2", "3"], format_func={"1": "普通用户", "2": "会员", "3": "管理员"}.get, key="adm_utype")
            if st.form_submit_button("新增", type="primary"):
                if not uname or not pwd:
                    st.warning("用户名和密码必填")
                else:
                    ok, msg = api.admin_user_add(
                        {"username": uname, "password": pwd, "nickName": nick or uname, "userType": int(utype)}
                    )
                    (st.toast if ok else st.error)(msg, icon=":material/check_circle:" if ok else None)
                    st.rerun()

# ---------------- 股票管理 ----------------

if tab_stock.open:
    st.session_state.setdefault("adm_stock_page", 1)
    params = {"pageNum": st.session_state.adm_stock_page, "pageSize": 15}
    if kw := st.text_input("代码/名称筛选", key="adm_stock_kw"):
        params["keyword"] = kw
    rows, total = api.admin_page("/api/admin/stock/page", params)
    if rows:
        df = pd.DataFrame(
            [
                {
                    "id": r.get("id"),
                    "symbol": r.get("symbol"),
                    "name": r.get("name"),
                    "industry": r.get("industry") or "-",
                    "marketType": r.get("marketType"),
                    "listDate": r.get("listDate") or "-",
                }
                for r in rows
            ]
        )
        styled = df.style.map(
            lambda v: "color: #E8EAED", subset=["symbol", "name"]
        )
        st.dataframe(
            styled, hide_index=True, width="stretch",
            column_config={
                "id": st.column_config.NumberColumn("ID", width="small"),
                "symbol": st.column_config.TextColumn("代码"),
                "name": st.column_config.TextColumn("名称"),
                "industry": st.column_config.TextColumn("行业"),
                "marketType": st.column_config.NumberColumn("市场类型"),
                "listDate": st.column_config.TextColumn("上市日期"),
            },
        )
    else:
        st.caption("无匹配股票")
    if (np := admin_pager("stock", st.session_state.adm_stock_page, total, 15)) is not None:
        st.session_state.adm_stock_page = np
        st.rerun()

    with st.expander(":material/edit: 修改股票信息（按代码幂等更新）"):
        with st.form("adm_stock_update", border=False):
            c1, c2, c3 = st.columns(3)
            sid = c1.number_input("股票 ID", min_value=1, step=1, key="adm_sid")
            ssym = c2.text_input("代码", key="adm_ssym")
            sname = c3.text_input("名称", key="adm_sname")
            c4, c5 = st.columns(2)
            sind = c4.text_input("行业", key="adm_sind")
            smkt = c5.number_input("市场类型", min_value=0, max_value=4, step=1, key="adm_smkt")
            if st.form_submit_button("更新", type="primary"):
                body = {"id": int(sid)}
                if ssym:
                    body["symbol"] = ssym
                if sname:
                    body["name"] = sname
                if sind:
                    body["industry"] = sind
                body["marketType"] = int(smkt)
                ok, msg = api.admin_stock_update(body)
                (st.toast if ok else st.error)(msg, icon=":material/check_circle:" if ok else None)
                st.rerun()

    with st.container(horizontal=True, horizontal_alignment="left"):
        if st.button("导入 A 股数据（Excel 全量）", icon=":material/upload_file:"):
            st.info("库内已有 5458 只股票；重复导入会使行数翻倍（原系统行为），请谨慎操作")

# ---------------- 博客 / 评论管理 ----------------

if tab_blog.open:
    st.session_state.setdefault("adm_blog_page", 1)
    params = {"pageNum": st.session_state.adm_blog_page, "pageSize": 15}
    rows, total = api.admin_page("/api/admin/blog/page", params)
    if rows:
        for b in rows:
            with st.container(border=True):
                m = st.container(horizontal=True, horizontal_alignment="left")
                st.markdown(
                    f"**{b.get('title', '')}**　"
                    f"<span style='color:#8B949E;font-size:12px'>作者ID {b.get('userId')} · "
                    f"{b.get('createTime', '')}</span>",
                    unsafe_allow_html=True,
                )
                if st.button("删除", key=f"adbdel_{b.get('id')}", icon=":material/delete:"):
                    ok, msg = api.admin_delete(f"/api/admin/blog/{b.get('id')}")
                    (st.toast if ok else st.error)(msg, icon=":material/check_circle:" if ok else None)
                    st.rerun()
    else:
        st.caption("暂无博客")
    if (np := admin_pager("blog", st.session_state.adm_blog_page, total, 15)) is not None:
        st.session_state.adm_blog_page = np
        st.rerun()

if tab_cmt.open:
    st.session_state.setdefault("adm_cmt_page", 1)
    params = {"pageNum": st.session_state.adm_cmt_page, "pageSize": 20}
    if bid := st.number_input("按博客 ID 筛选（0=全部）", min_value=0, step=1, key="adm_cmt_bid"):
        params["blogId"] = int(bid)
    rows, total = api.admin_page("/api/admin/blog/comments/page", params)
    if rows:
        df = pd.DataFrame(
            [
                {
                    "id": c.get("id"),
                    "blogId": c.get("blogId"),
                    "userId": c.get("userId"),
                    "content": (c.get("content") or "")[:40],
                    "liked": c.get("liked"),
                    "createTime": c.get("createTime"),
                    "action": f":material/delete: 删除 {c.get('id')}",
                }
                for c in rows
            ]
        )

        def _on_cmt_action() -> None:
            click = st.session_state.adm_cmt_action
            if click and click.label:
                cid = int(str(click.label).split()[-1])
                ok, msg = api.admin_delete(f"/api/admin/blog/comments/{cid}")
                st.toast(msg, icon=":material/check_circle:" if ok else ":material/error:")

        st.dataframe(
            df, hide_index=True, width="stretch",
            column_config={
                "id": st.column_config.NumberColumn("ID", width="small"),
                "blogId": st.column_config.NumberColumn("博客ID", width="small"),
                "userId": st.column_config.NumberColumn("用户ID", width="small"),
                "content": st.column_config.TextColumn("内容"),
                "liked": st.column_config.NumberColumn("点赞数"),
                "createTime": st.column_config.TextColumn("时间"),
                "action": st.column_config.ButtonColumn("操作", on_click=_on_cmt_action, key="adm_cmt_action", type="secondary"),
            },
        )
    else:
        st.caption("暂无评论")
    if (np := admin_pager("cmt", st.session_state.adm_cmt_page, total, 20)) is not None:
        st.session_state.adm_cmt_page = np
        st.rerun()

# ---------------- 交易管理 ----------------

if tab_trade.open:
    st.session_state.setdefault("adm_ord_page", 1)
    st.session_state.setdefault("adm_deal_page", 1)
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("委托记录")
        params = {"pageNum": st.session_state.adm_ord_page, "pageSize": 15}
        if fkw := st.text_input("按用户/代码过滤（如 600519）", key="adm_ord_kw"):
            params["symbol"] = fkw
        rows, total = api.admin_page("/api/admin/trade/order/page", params)
        if rows:
            df = pd.DataFrame(
                [
                    {
                        "orderNo": o.get("orderNo"),
                        "userId": o.get("userId"),
                        "symbol": o.get("symbol"),
                        "方向": "买" if o.get("direction") == 1 else "卖",
                        "price": o.get("price"),
                        "quantity": o.get("quantity"),
                        "status": o.get("status"),
                        "createTime": o.get("createTime"),
                    }
                    for o in rows
                ]
            )
            st.dataframe(
                df, hide_index=True, width="stretch",
                column_config={
                    "price": st.column_config.NumberColumn("价格", format="%.2f"),
                    "quantity": st.column_config.NumberColumn("数量(手)"),
                },
            )
        else:
            st.caption("暂无委托")
        if (np := admin_pager("ord", st.session_state.adm_ord_page, total, 15)) is not None:
            st.session_state.adm_ord_page = np
            st.rerun()
    with c2:
        st.subheader("成交记录")
        params = {"pageNum": st.session_state.adm_deal_page, "pageSize": 15}
        if fkw := st.text_input("按用户/代码过滤（如 600519）", key="adm_deal_kw"):
            params["symbol"] = fkw
        rows, total = api.admin_page("/api/admin/trade/deal/page", params)
        if rows:
            df = pd.DataFrame(
                [
                    {
                        "dealNo": d.get("dealNo"),
                        "userId": d.get("userId"),
                        "symbol": d.get("symbol"),
                        "方向": "买" if d.get("dealDirection") == 1 else "卖",
                        "price": d.get("price"),
                        "quantity": d.get("quantity"),
                        "createTime": d.get("createTime"),
                    }
                    for d in rows
                ]
            )
            st.dataframe(
                df, hide_index=True, width="stretch",
                column_config={
                    "price": st.column_config.NumberColumn("价格", format="%.2f"),
                    "quantity": st.column_config.NumberColumn("数量(手)"),
                },
            )
        else:
            st.caption("暂无成交")
        if (np := admin_pager("deal", st.session_state.adm_deal_page, total, 15)) is not None:
            st.session_state.adm_deal_page = np
            st.rerun()
