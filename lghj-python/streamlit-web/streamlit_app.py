# -*- coding: utf-8 -*-
"""streamlit_app.py —— 「量股化金」Streamlit 前端入口

- 同花顺风格深色行情终端（涨红跌绿），替代原 Vue 前端对接同一套 Python 三后端
- 登录/注册在独立「登录」页面（未登录时出现在导航首位）；侧栏仅显示用户卡片
- userType=3 追加「管理端」页面组
- 启动：streamlit run streamlit_app.py --server.port 8501
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="量股化金 · 模拟炒股终端",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

import api  # noqa: E402  (set_page_config 必须先于其它 st 命令)

# ---------------- 页面导航（先于侧栏 page_link 注册） ----------------

login_pages = [
    st.Page("app_pages/登录-login.py", title="登录 / 注册", icon=":material/login:"),
]
trade_pages = [
    st.Page("app_pages/行情-market.py", title="行情", icon=":material/monitoring:"),
    st.Page("app_pages/个股-stock.py", title="个股", icon=":material/candlestick_chart:"),
    st.Page("app_pages/交易-trade.py", title="模拟交易", icon=":material/swap_horiz:"),
    st.Page("app_pages/自选-watchlist.py", title="自选股", icon=":material/star:"),
]
smart_pages = [
    st.Page("app_pages/AI投顾-advisor.py", title="AI 投顾", icon=":material/smart_toy:"),
    st.Page("app_pages/社区-community.py", title="社区", icon=":material/forum:"),
]
admin_pages = [
    st.Page("app_pages/管理端-admin.py", title="管理端", icon=":material/admin_panel_settings:"),
]

pages: dict
if not st.session_state.get("token"):
    # 未登录：独立登录屏（仅登录页，应用内其余页面与侧栏由登录页隐藏）
    pages = {"": login_pages}
else:
    pages = {
        "交易终端": trade_pages,
        "智能服务": smart_pages,
    }
    if (st.session_state.get("user") or {}).get("userType") == 3:
        pages["管理"] = admin_pages

st.navigation(pages, position="sidebar").run()


# ---------------- 侧栏（导航已注册，page_link 可用） ----------------

def render_user_card() -> None:
    user = st.session_state.get("user") or {}
    with st.container(border=True):
        st.markdown(
            f"**{user.get('username', '')}**　"
            f"<span style='color:#8B949E;font-size:12px'>{user.get('identityDesc', '')}</span>",
            unsafe_allow_html=True,
        )
        if st.button("退出登录", icon=":material/logout:", use_container_width=True):
            api.logout()
            st.rerun()


with st.sidebar:
    st.markdown(
        "<div style='display:flex;align-items:center;gap:8px;padding:4px 0 10px 0'>"
        "<span style='font-size:22px'>📈</span>"
        "<span style='font-size:17px;font-weight:700;color:#E64545'>量股化金</span>"
        "<span style='font-size:11px;color:#8B949E'>模拟炒股终端</span></div>",
        unsafe_allow_html=True,
    )
    if st.session_state.get("token"):
        render_user_card()
    else:
        with st.container(border=True):
            st.caption("未登录 · 行情可匿名浏览")
            st.page_link(
                "app_pages/登录-login.py",
                label="去登录 / 注册",
                icon=":material/login:",
            )
