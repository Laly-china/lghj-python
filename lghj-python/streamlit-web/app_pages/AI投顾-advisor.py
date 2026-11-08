# -*- coding: utf-8 -*-
"""AI 投顾页 —— 管家团队对话 + 执行过程可视化

与侧栏联动（streamlit_app.py）：
- 侧栏「管家团队」点击管家 → 本页与该管家单独对话（默认队长自动调度专家）；
- 侧栏「历史对话」点击会话 → 本页回看历史消息与思考过程（可续聊）；
- 顶栏「新建对话」回到队长默认态。
执行过程可视化（ZCode 式：思考过程位于回答之前）：
- 每条回答气泡内上方「已深度思考 · N 步」折叠面板（🧠决策/🔧工具/➡️转交/📤输出芯片）；
- 生成期间同位置实时流出「深度思考中…·已N步」+ 右上角「哪几位管家正在工作」指示。
"""

from concurrent.futures import ThreadPoolExecutor

import streamlit as st

import api
import components as ui

DEFAULT_AGENT = "investment-advisor"

st.header("AI 投顾", icon=":material/smart_toy:")

ui.require_login()

user = st.session_state.get("user") or {}
user_id = int(user.get("id") or 0)

# 当前模型徽标（多模型选择：用户自配 > 系统默认；在「模型设置」页切换）
_cfg_model = api.model_config_active()
st.caption(
    f"当前模型：{(_cfg_model.get('name') + '（' + _cfg_model.get('model') + '）') if _cfg_model else '系统默认（deepseek-chat）'}"
    "　·　可在「模型设置」页切换"
)

agents = api.agent_config_list()
if not agents:
    st.warning("智能体服务不可用或未配置（请确认 8091 已启动）")
    st.stop()

# ---------------- 侧栏联动：历史会话回看 / 管家选择 ----------------

_open_h = st.session_state.pop("advisor_open_history", None)
if _open_h:
    _sid = _open_h.get("sessionId")
    _h_agent = _open_h.get("agentId") or DEFAULT_AGENT
    st.session_state.advisor_current_agent = _h_agent
    st.session_state.advisor_last_agent = _h_agent
    st.session_state.advisor_session = _sid
    st.session_state.chat_running = False
    st.session_state.chat_future = None
    _msgs = api.agent_history_messages(_sid)
    st.session_state.advisor_messages = [
        {"role": m.get("role"), "content": m.get("content", ""), "trace": m.get("trace") or []}
        for m in _msgs
    ]

_pick = st.session_state.pop("advisor_agent_pick", None)
if _pick:
    st.session_state.advisor_current_agent = _pick

agent_id = st.session_state.get("advisor_current_agent", DEFAULT_AGENT)

# 切换管家 → 重置会话与消息（新建对话语义）
if st.session_state.get("advisor_last_agent") != agent_id:
    st.session_state.advisor_last_agent = agent_id
    st.session_state.pop("advisor_session", None)
    st.session_state.pop("advisor_messages", None)
    st.session_state.chat_running = False
    st.session_state.chat_future = None

if "advisor_messages" not in st.session_state:
    st.session_state.advisor_messages = []


# 后台对话执行器（LLM 含工具往返可达数十秒，避免阻塞页面脚本）
@st.cache_resource
def _chat_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-chat")


def _finalize_if_done() -> bool:
    """后台对话已完成则落消息与轨迹，返回 True（调用方随后整体重跑页面）。"""
    future = st.session_state.get("chat_future")
    if future is None or not st.session_state.get("chat_running") or not future.done():
        return False
    try:
        ok, content = future.result()
    except Exception as exc:  # noqa: BLE001
        ok, content = False, f"智能体请求异常：{exc}"
    seg: list[dict] = []
    try:
        events = api.agent_trace(agent_id, user_id, st.session_state.get("advisor_session") or "")
        seg = ui.slice_current_run(events)
    except Exception:  # noqa: BLE001 轨迹拉取失败不影响回答展示
        seg = []
    st.session_state.advisor_messages.append({
        "role": "assistant",
        "content": content if (ok and content) else (content or "智能体暂不可用"),
        "trace": seg,
    })
    st.session_state.chat_future = None
    st.session_state.chat_running = False
    return True


def _submit_question(text: str) -> None:
    """提交一轮提问（推荐 pills 与聊天输入框共用）：落消息 → 建会话 → 后台执行 → 进入实时轮询态。"""
    st.session_state.advisor_messages.append({"role": "user", "content": text})
    if not st.session_state.get("advisor_session"):
        st.session_state.advisor_session = api.agent_session(agent_id, user_id)
    session_id = st.session_state.get("advisor_session")
    if not session_id:
        st.session_state.advisor_messages.append(
            {"role": "assistant", "content": "创建智能体会话失败", "trace": []}
        )
        st.rerun()
    st.session_state.chat_future = _chat_executor().submit(
        api.agent_chat, agent_id, user_id, session_id, text
    )
    st.session_state.chat_running = True
    st.rerun()


# ---------------- 顶栏：当前管家（新建对话在侧栏最顶部） ----------------

_card_name, _icon, _duty = ui.agent_card(agent_id)
_desc = _duty or ("全局投顾 · 调度 6 位专家" if agent_id == DEFAULT_AGENT else "")

st.markdown(
    f"<span style='font-size:22px'>{_icon}</span>　"
    f"<b style='font-size:16px'>{_card_name}</b>　"
    f"<span style='color:#6B7280;font-size:12px'>{_desc}</span>",
    unsafe_allow_html=True,
)

# ---------------- 专家团权重（仅队长/投资顾问智能体；权重按用户独立保存） ----------------


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
                f"<span style='color:#6B7280;font-size:12px'>{key}</span><br>"
                f"<span style='color:#6B7280;font-size:12px'>{m.get('desc', '')}</span>",
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


if agent_id == DEFAULT_AGENT:
    _et_cfg = api.expert_team_config(user_id) or {}
    _et_members = _et_cfg.get("members") or []
    with st.container(border=True):
        left, right = st.columns([4, 1])
        with left:
            st.markdown("**专家团**（6 位固定角色 · 权重可调）")
            if _et_members:
                _wtxt = "　".join(
                    f"<span style='font-size:12px;color:#6B7280'>{m['name']}</span>"
                    f"<span style='font-size:12px;color:#E64545;font-weight:600'>"
                    f" {m['weight']}%</span>"
                    for m in _et_members
                )
                st.markdown(_wtxt, unsafe_allow_html=True)
            st.caption(
                "已自定义权重：AI 将按权重加权汇总各专家意见" if _et_cfg.get("isCustom")
                else "当前为默认均分权重，点击右侧自定义"
            )
        with right:
            if st.button("调整权重", icon=":material/tune:", use_container_width=True):
                expert_team_dialog()

# ---------------- 对话区（思考过程在回答之前：ZCode 式） ----------------

for msg in st.session_state.advisor_messages:
    with st.chat_message(
        msg["role"],
        avatar=":material/person:" if msg["role"] == "user" else ":material/smart_toy:",
    ):
        if msg["role"] == "assistant" and msg.get("trace"):
            ui.agent_thinking_stream(msg["trace"], live=False)
        st.markdown(msg["content"])

SUGGESTIONS = {
    ":material/monitoring: 大盘怎么样？": "今天大盘走势如何，适合加仓吗？",
    ":material/account_balance_wallet: 分析我的持仓": "结合我的模拟持仓和交易画像，给我一些调仓建议",
    ":material/school: 新手学炒股": "我是新手，应该怎么开始学炒股，如何控制风险？",
}

if not st.session_state.advisor_messages and not st.session_state.get("chat_running"):
    selected = st.pills("试试这些", list(SUGGESTIONS.keys()), label_visibility="collapsed")
    if selected:
        _submit_question(SUGGESTIONS[selected])

# ---------------- 生成中：实时状态（右上角工作指示 + 思考芯片流） ----------------

if st.session_state.get("chat_running"):

    @st.fragment(run_every=2)
    def live_team_status() -> None:
        if _finalize_if_done():
            st.rerun()
        try:
            events = api.agent_trace(agent_id, user_id, st.session_state.get("advisor_session") or "")
        except Exception:  # noqa: BLE001 轮询失败不中断
            events = []
        seg = ui.slice_current_run(events)

        # 右上角工作指示（ZCode 式：哪几位管家正在干活）
        _status = ui.agent_team_status(seg, running=True)
        _working = [ui.agent_card(a)[0] for a, s in _status.items() if s == "running"]
        with st.container(horizontal=True, horizontal_alignment="right"):
            if _working:
                st.markdown(
                    f"<span style='color:#D97706;font-size:12px'>⚡ {'、'.join(_working)} 正在工作</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<span style='color:#6B7280;font-size:12px'>⏳ 正在拆解问题…</span>",
                    unsafe_allow_html=True,
                )

        with st.chat_message("assistant", avatar=":material/smart_toy:"):
            # 实时思考芯片流（ZCode 式：🧠决策/🔧工具/➡️转交/📤输出，随轨迹每 2 秒流出）
            ui.agent_thinking_stream(seg, live=True)

    live_team_status()
    st.stop()  # 生成期间收起输入框，防止并发提问

# ---------------- 输入与提交（后台执行 + 实时点灯；与推荐 pills 共用 _submit_question） ----------------

if prompt := st.chat_input(f"向{_card_name}提问（行情 / 持仓 / 交易策略…）", submit_mode="disable"):
    _submit_question(prompt)

with st.container(horizontal=True, horizontal_alignment="right"):
    if st.button("清空对话", icon=":material/delete_sweep:"):
        st.session_state.pop("advisor_messages", None)
        st.session_state.pop("advisor_session", None)
        st.session_state.chat_running = False
        st.session_state.chat_future = None
        st.rerun()
