# -*- coding: utf-8 -*-
"""AI 投顾页 —— 智能体对话（8091：YAML 装配的 6 专家 + Supervisor）"""

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
