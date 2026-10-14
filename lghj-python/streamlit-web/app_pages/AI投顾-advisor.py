# -*- coding: utf-8 -*-
"""AI 投顾页 —— 智能体对话（8091：YAML 装配的 6 专家 + Supervisor）+ 专家团权重配置"""

import streamlit as st

import api
import components as ui

st.header("AI 投顾", icon=":material/smart_toy:")

ui.require_login()

user = st.session_state.get("user") or {}
user_id = int(user.get("id") or 0)

agents = api.agent_config_list()
if not agents:
    st.warning("智能体服务不可用或未配置（请确认 8091 已启动）")
    st.stop()

# ---------------- 专家团权重配置 ----------------
# 需求：成员人数与角色固定，用户仅可调整各成员权重，以获得符合个人预期的投资计划。
# 权重按用户独立保存，并在最终回复中按权重加权汇总（输出层加权）。

ADVISOR_AGENT_ID = next(
    (a.get("agentId") for a in agents if a.get("agentId") == "investment-advisor"),
    agents[0].get("agentId") if agents else "",
)


@st.dialog("专家团配置", width="large")
def expert_team_dialog() -> None:
    st.caption(
        "专家团由 6 位固定角色组成（人数与职责不可变更）。"
        "你可以调整每位专家的**意见权重**，AI 将按权重加权汇总，生成符合你个人预期的投资计划。"
        "权重合计须为 100%。"
    )
    cfg = api.expert_team_config(user_id)
    if not cfg:
        st.error("读取专家团配置失败，请确认 8091 服务已启动")
        return
    members = cfg.get("members") or []
    st.caption(
        f"当前状态：{'已自定义' if cfg.get('isCustom') else '默认均分'}　·　"
        f"合计 {cfg.get('totalWeight', 100)}%"
    )
    st.divider()
    new_weights: dict[str, int] = {}
    for m in members:
        key = m["key"]
        col_a, col_b = st.columns([2.6, 1.6])
        with col_a:
            st.markdown(
                f"**{m['name']}**　"
                f"<span style='color:#8B949E;font-size:12px'>{key}</span><br>"
                f"<span style='color:#8B949E;font-size:12px'>{m.get('desc', '')}</span>",
                unsafe_allow_html=True,
            )
        with col_b:
            new_weights[key] = st.slider(
                m["name"],
                min_value=0,
                max_value=100,
                value=int(m.get("weight") or 0),
                step=1,
                key=f"exp_w_{key}",
                label_visibility="collapsed",
            )
    total = sum(new_weights.values())
    hint = "权重合计正确" if total == 100 else f"权重合计 {total}%（需调整为 100%）"
    (st.success if total == 100 else st.warning)(hint)

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("保存权重", type="primary", use_container_width=True):
            ok, _cfg, msg = api.expert_team_update(user_id, new_weights)
            if ok:
                st.toast("专家团权重已保存", icon=":material/check_circle:")
                st.rerun()
            else:
                st.error(msg)
    with c2:
        if st.button("平均分配", use_container_width=True):
            n = len(members)
            base, rem = 100 // n, 100 - (100 // n) * n
            for i, m in enumerate(members):
                st.session_state[f"exp_w_{m['key']}"] = base + (1 if i < rem else 0)
            st.rerun()
    with c3:
        if st.button("恢复默认", use_container_width=True):
            api.expert_team_reset(user_id)
            for m in members:
                st.session_state.pop(f"exp_w_{m['key']}", None)
            st.toast("已恢复默认权重", icon=":material/restart_alt:")
            st.rerun()


# ---------------- 智能体选择 ----------------

agent_options = {a.get("agentName", a.get("agentId", "")): a.get("agentId", "") for a in agents}
with st.container(horizontal=True, horizontal_alignment="left"):
    sel_name = st.selectbox(
        "智能体", list(agent_options.keys()), key="advisor_agent",
        label_visibility="collapsed",
    )
    st.caption(next(
        (a.get("agentDesc", "") for a in agents if a.get("agentId") == agent_options[sel_name]), ""
    ))
agent_id = agent_options[sel_name]

# 专家团入口（仅投资顾问智能体支持）
if agent_id == "investment-advisor":
    cfg = api.expert_team_config(user_id) or {}
    members = cfg.get("members") or []
    with st.container(border=True):
        left, right = st.columns([4, 1])
        with left:
            st.markdown("**专家团**（6 位固定角色 · 权重可调）")
            if members:
                wtxt = "　".join(
                    f"<span style='font-size:12px;color:#8B949E'>{m['name']}</span>"
                    f"<span style='font-size:12px;color:#E64545;font-weight:600'>"
                    f" {m['weight']}%</span>"
                    for m in members
                )
                st.markdown(wtxt, unsafe_allow_html=True)
            st.caption(
                "已自定义权重：AI 将按权重加权汇总各专家意见" if cfg.get("isCustom")
                else "当前为默认均分权重，点击右侧自定义"
            )
        with right:
            if st.button("调整权重", icon=":material/tune:", use_container_width=True):
                expert_team_dialog()

# 会话：同 userId 幂等复用（后端内存 Map）
if st.session_state.get("advisor_agent_id") != agent_id:
    st.session_state.pop("advisor_session", None)
    st.session_state.pop("advisor_messages", None)
    st.session_state.advisor_agent_id = agent_id

if "advisor_messages" not in st.session_state:
    st.session_state.advisor_messages = []

SUGGESTIONS = {
    ":material/monitoring: 大盘怎么样？": "今天大盘走势如何，适合加仓吗？",
    ":material/account_balance_wallet: 分析我的持仓": "结合我的模拟持仓和交易画像，给我一些调仓建议",
    ":material/school: 新手学炒股": "我是新手，应该怎么开始学炒股，如何控制风险？",
}

# ---------------- 对话区 ----------------

for msg in st.session_state.advisor_messages:
    with st.chat_message(msg["role"], avatar=":material/person:" if msg["role"] == "user" else ":material/smart_toy:"):
        st.markdown(msg["content"])

if not st.session_state.advisor_messages:
    selected = st.pills("试试这些", list(SUGGESTIONS.keys()), label_visibility="collapsed")
    if selected:
        st.session_state.advisor_messages.append({"role": "user", "content": SUGGESTIONS[selected]})
        st.rerun()

if prompt := st.chat_input("向投顾提问（行情 / 持仓 / 交易策略…）", submit_mode="disable"):
    st.session_state.advisor_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(prompt)
    with st.chat_message("assistant", avatar=":material/smart_toy:"):
        if not st.session_state.get("advisor_session"):
            st.session_state.advisor_session = api.agent_session(agent_id, user_id)
        session_id = st.session_state.get("advisor_session")
        if not session_id:
            st.error("创建智能体会话失败")
        else:
            with st.spinner("投顾分析中…（会调用行情/画像工具，可能需要数十秒）"):
                ok, content = api.agent_chat(agent_id, user_id, session_id, prompt)
            if ok and content:
                st.markdown(content)
                st.session_state.advisor_messages.append({"role": "assistant", "content": content})
            else:
                st.error(content or "智能体暂不可用")

with st.container(horizontal=True, horizontal_alignment="right"):
    if st.button("清空对话", icon=":material/delete_sweep:"):
        st.session_state.pop("advisor_messages", None)
        st.session_state.pop("advisor_session", None)
        st.rerun()
