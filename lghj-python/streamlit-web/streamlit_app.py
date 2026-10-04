# -*- coding: utf-8 -*-
"""streamlit_app.py —— 「量股化金」Streamlit 前端入口

- 同花顺风格深色行情终端（涨红跌绿），替代原 Vue 前端对接同一套 Python 三后端
- 马维斯式侧栏（登录后）：管家团队（队长 + 6 专家，点击即单独对话）/ 个人知识库
  （上传 txt/md、删除）/ 历史对话（可滑动，点击回看）/ 账户卡片固定左下角
- 登录/注册在独立「登录」页面（未登录时出现在导航首位）
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

# ---------------- 侧栏（马维斯式：管家团队 / 知识库 / 历史 / 底部账户卡） ----------------
# 必须先于页面渲染：页面脚本里的 st.stop()（如自选股为空、交易页未开户）会中断
# 整个脚本，若侧栏写在 .run() 之后就会随之被砍掉（置顶栏消失、原生导航复现）。

# 账户行固定左下角（用户信息 + 退出图标同一行，ZCode 式）+ 侧栏内容底部预留高度
# 锚定技巧：账户行用绝对定位相对侧栏本身（stSidebar 内联宽度随拉伸实时更新，
# left:0/right:0 自动跟随），故须把中间的 relative 祖先（滚动容器 stSidebarContent、
# 卡片所属 stElementContainer）转为 static，避免卡片锚错父级/随内容滚动。
st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] > div[data-testid="stSidebarContent"] {
        position: static !important; padding-bottom: 58px;
    }
    section[data-testid="stSidebar"] .stElementContainer:has(.lghj-account-card) {
        position: static !important;
    }
    .lghj-account-card {
        position: absolute; left: 0; right: 0; bottom: 0; z-index: 400;
        background: #FFFFFF; border-top: 1px solid #E2E5E9;
        padding: 8px 50px 8px 12px;
    }
    /* 退出图标按钮钉在账户行右端（随侧栏宽度跟随） */
    section[data-testid="stSidebar"] .st-key-side_logout {
        position: absolute !important; left: auto; right: 10px; bottom: 8px; z-index: 401;
    }
    /* 隐藏框架自动注入的侧栏导航（固定渲染在顶部，无法排到管家团队之后），
       页面导航改由下方 st.page_link 自渲染，保证「品牌→新建对话→管家团队」置顶 */
    [data-testid="stSidebarNav"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        "<div style='display:flex;align-items:center;gap:8px;padding:4px 0 8px 0'>"
        "<span style='font-size:22px'>📈</span>"
        "<span style='font-size:17px;font-weight:700;color:#E64545'>量股化金</span>"
        "<span style='font-size:11px;color:#6B7280'>模拟炒股终端</span></div>",
        unsafe_allow_html=True,
    )

# 侧栏管家清单（agentId, 图标, 侧栏短名；职能详情见 AI 投顾页卡片条）
_SIDE_AGENTS = [
    ("investment-advisor", "👑", "队长"),
    ("MarketAnalysisAgent", "🌐", "行情管家"),
    ("QuantTechnicalAgent", "📈", "技术管家"),
    ("PersonalTradeProfileAgent", "💼", "持仓管家"),
    ("RiskAssessmentAgent", "🛡️", "风控管家"),
    ("PortfolioAdviceAgent", "🧩", "组合管家"),
    ("ComplianceDisclosureAgent", "⚖️", "合规管家"),
]

if st.session_state.get("token"):
    user = st.session_state.get("user") or {}
    uid = user.get("id")

    with st.sidebar:
        # ---- 新建对话（侧栏最顶部：回到队长模式，由队长自动思考拆解并分配专家） ----
        if st.button("新建对话", icon=":material/add:", use_container_width=True,
                     type="primary", key="side_new_chat"):
            st.session_state.advisor_agent_pick = "investment-advisor"
            st.session_state.pop("advisor_open_history", None)
            st.session_state.pop("advisor_session", None)
            st.session_state.pop("advisor_messages", None)
            st.session_state.chat_running = False
            st.session_state.chat_future = None
            st.switch_page("app_pages/AI投顾-advisor.py")

        # ---- 管家团队（折叠式，默认收起；点击管家即单独对话并自动收起） ----
        with st.expander("管家团队", expanded=False, key="side_team_exp"):
            _c1, _c2 = st.columns(2)
            for _i, (_aid, _icon, _label) in enumerate(_SIDE_AGENTS):
                with (_c1 if _i % 2 == 0 else _c2):
                    if st.button(f"{_icon} {_label}", key=f"side_agent_{_aid}", use_container_width=True):
                        st.session_state.advisor_agent_pick = _aid
                        st.session_state.pop("advisor_open_history", None)
                        try:
                            st.session_state["side_team_exp"] = False  # 选中后收起
                        except Exception:  # noqa: BLE001 旧版 expander 状态语义兼容
                            pass
                        st.switch_page("app_pages/AI投顾-advisor.py")

        # ---- 页面导航（自渲染，排在置顶栏之下：行情 / 交易 / AI 投顾…） ----
        st.divider()
        for _group, _plist in pages.items():
            if _group:
                st.caption(_group)
            for _p in _plist:
                st.page_link(_p, use_container_width=True)

        # ---- 个人知识库（上传 / 删除，投顾可检索引用） ----
        st.divider()
        st.caption("个人知识库")
        _up = st.file_uploader("上传 txt / md 文档", type=["txt", "md"],
                               key="side_kb_up", label_visibility="collapsed")
        if _up is not None:
            ok, msg = api.agent_kb_upload(uid, _up.name, _up.getvalue())
            if ok:
                st.toast(msg, icon=":material/check_circle:")
            else:
                st.error(msg)
            st.session_state.pop("side_kb_up", None)
            st.rerun()
        for _doc in api.agent_kb_list(uid):
            _k1, _k2 = st.columns([5, 1])
            _k1.caption(f":material/description: {_doc.get('title', '')} · {_doc.get('charCount', 0)} 字")
            if _k2.button("✕", key=f"side_kbdel_{_doc.get('id')}", help="移除文档"):
                api.agent_kb_delete(_doc.get("id"), uid)
                st.rerun()

        # ---- 历史对话（固定高度可滑动，点击回看/续聊） ----
        st.divider()
        with st.container(height=200):
            st.caption("历史对话")
            for _s in api.agent_history_list(uid):
                _h1, _h2 = st.columns([5, 1])
                if _h1.button(_s.get("title", "新对话"), key=f"side_hist_{_s.get('sessionId')}",
                              use_container_width=True,
                              help=f"{_s.get('agentId', '')} · {_s.get('updateTime', '')}"):
                    st.session_state.advisor_open_history = {
                        "sessionId": _s.get("sessionId"),
                        "agentId": _s.get("agentId") or "investment-advisor",
                    }
                    st.switch_page("app_pages/AI投顾-advisor.py")
                if _h2.button("🗑", key=f"side_histdel_{_s.get('sessionId')}", help="删除会话"):
                    api.agent_history_delete(_s.get("sessionId"), uid)
                    st.rerun()

        # ---- 账户行（固定左下角：头像 + 用户名 + 角色徽章 + 退出图标，ZCode 式） ----
        st.markdown(
            f"""
            <div class="lghj-account-card">
              <div style="display:flex;align-items:center;gap:9px">
                <div style="width:32px;height:32px;border-radius:50%;background:#F3F4F6;
                            display:flex;align-items:center;justify-content:center;font-size:16px">👤</div>
                <div style="display:flex;align-items:center;gap:6px;min-width:0">
                  <span style="font-weight:700;font-size:13px;color:#1F2328;white-space:nowrap;
                               overflow:hidden;text-overflow:ellipsis;max-width:110px">{user.get('username', '')}</span>
                  <span style="font-size:10px;color:#6B7280;background:#F3F4F6;border:1px solid #E2E5E9;
                               border-radius:8px;padding:1px 7px;white-space:nowrap">{user.get('identityDesc', '')}</span>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("", icon=":material/logout:", key="side_logout", help="退出登录"):
            api.logout()
            st.rerun()
else:
    with st.sidebar:
        with st.container(border=True):
            st.caption("未登录 · 行情可匿名浏览")
            st.page_link(login_pages[0], label="去登录 / 注册")

# ---------------- 页面渲染（最后执行：页面脚本可安全 st.stop()） ----------------

st.navigation(pages, position="sidebar").run()
