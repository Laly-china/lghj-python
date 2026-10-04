# -*- coding: utf-8 -*-
"""登录页 —— 独立的登录/注册页面（原 Vue Login.vue 的对应物）

未登录时在导航中出现；登录成功后跳转行情页。
右上角为缩小版品牌图标（自定义 HTML，用户已解除仅用 Streamlit 原生元素的限制）。
"""

import streamlit as st

import api

# 独立登录屏：隐藏侧栏与应用导航，与主应用（首页）完全分离
st.html(
    """
    <style>
      [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
      }
      section[data-testid="stMain"] {
        margin-left: 0 !important;
      }
    </style>
    """
)

# ---------------- 右上角缩小版品牌图标 ----------------

col_spacer, col_logo = st.columns([4, 1])
with col_logo:
    st.html(
        """
        <div style="display:flex; justify-content:flex-end; align-items:center; gap:9px">
          <div style="text-align:right; line-height:1.25">
            <div style="font-size:14px; font-weight:700; color:#E64545; letter-spacing:2px">量股化金</div>
            <div style="font-size:10px; color:#6B7280; letter-spacing:1px">模拟炒股终端</div>
          </div>
          <div style="
              width:40px; height:40px; border-radius:10px; flex:none;
              background: linear-gradient(135deg, #b3222a 0%, #e64545 55%, #f0674f 100%);
              display:flex; align-items:center; justify-content:center;
              font-size:21px; box-shadow:0 2px 8px rgba(230,69,69,0.35);
              overflow:hidden; position:relative;">
            <div style="font-size:21px; line-height:1">📈</div>
            <div style="position:absolute; right:-12px; top:-12px; width:30px; height:30px;
                        border-radius:50%; background:rgba(255,255,255,0.15)"></div>
          </div>
        </div>
        """
    )

# ---------------- 居中卡片 ----------------

if st.session_state.get("token"):
    st.rerun()  # 重跑后导航按已登录重建，根 URL 自然落到行情页

st.markdown(
    "<div style='text-align:center; margin: 26px 0 14px 0'>"
    "<span style='font-size:22px; font-weight:800; letter-spacing:4px'>欢迎登录</span></div>",
    unsafe_allow_html=True,
)

col_l, col_card, col_r = st.columns([1, 1.4, 1])
with col_card:
    tab_login, tab_reg = st.tabs(["登 录", "注 册"])

    with tab_login:
        with st.form("login_form", border=True):
            st.markdown("##### 账号登录")
            u = st.text_input("用户名", key="login_user", placeholder="admin")
            p = st.text_input("密码", type="password", key="login_pwd")
            if st.form_submit_button("登 录", type="primary", use_container_width=True):
                if not u or not p:
                    st.warning("请输入用户名和密码")
                else:
                    ok, msg = api.login(u, p)
                    if ok:
                        st.toast(msg, icon=":material/check_circle:")
                        st.rerun()  # 导航按已登录重建后，根 URL 落到行情页
                    else:
                        st.error(msg)
        st.caption("演示管理员：admin / 123456 · 普通用户可在「注册」自助创建")

    with tab_reg:
        with st.form("register_form", border=True):
            st.markdown("##### 注册新账号")
            u = st.text_input("用户名", key="reg_user")
            p = st.text_input("密码", type="password", key="reg_pwd")
            nick = st.text_input("昵称（可选）", key="reg_nick")
            if st.form_submit_button("注 册", type="primary", use_container_width=True):
                if not u or not p:
                    st.warning("请输入用户名和密码")
                else:
                    ok, msg = api.register(u, p, nick_name=nick)
                    if ok:
                        st.success(msg + "，请切换到「登 录」")
                    else:
                        st.error(msg)

st.caption(
    "登录后可用：模拟交易 · 自选股 · AI 投顾 · 社区发帖 · （管理员）管理端　|　"
    "行情与个股数据无需登录"
)
