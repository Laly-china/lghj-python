# -*- coding: utf-8 -*-
"""main.py —— 「量股化金」AI 投顾终端（agent-web，NiceGUI，端口 8502）

参考腾讯 Marvis 的界面结构（纯 Python 实现，UI 层基于 NiceGUI/Quasar）：
- 左侧固定栏：品牌 → 新建对话 → 管家团队（7 个可单独对话的 Agent）→ 知识库 →
  历史对话（可滑动）→ 底部固定账户卡片；
- 主区默认「新建对话」：发问后实时显示思考过程（LLM 决策 / 工具调用 / 转交芯片，
  参考 ZCode 对话界面的可折叠工具芯片），右上角可折叠图标提示哪几个 Agent 正在干活，
  回答以 Markdown 渲染；生成期间用户可滚动查看，不用干等；
- 历史会话与个人知识库经 8091 扩展接口持久化在 MySQL。

启动：venv 的 python main.py（或 启动投顾终端-run-agent-web.bat）
"""

from __future__ import annotations

import asyncio
import json
import time

from nicegui import app, run, ui

import api_client

# 管家卡片命名（与 Streamlit components.AGENT_CARDS 保持一致）
AGENT_CARDS: dict[str, tuple[str, str, str]] = {
    "InvestmentAdvisorSupervisor": ("队长", "👑", "拆解问题、分派专家、汇总结论"),
    "MarketAnalysisAgent": ("行情管家", "🌐", "宏观·行业·基本面与消息面"),
    "QuantTechnicalAgent": ("技术管家", "📈", "量价趋势·支撑阻力·波动分析"),
    "PersonalTradeProfileAgent": ("持仓管家", "💼", "我的持仓与交易画像"),
    "RiskAssessmentAgent": ("风控管家", "🛡️", "风险识别与仓位风控边界"),
    "PortfolioAdviceAgent": ("组合管家", "🧩", "配置建议·仓位纪律·观察清单"),
    "ComplianceDisclosureAgent": ("合规管家", "⚖️", "合规审查与免责声明"),
}
DEFAULT_AGENT = "investment-advisor"

# 轨迹事件芯片样式：emoji + 中文标签
_EVENT_BADGES = {
    "llm_call": "🧠",
    "transfer": "➡️",
    "tool": "🔧",
    "agent_text": "📤",
}

# 选中管家卡片的高亮样式
_SEL_CLASS = "bg-[#33191B] border border-[#E64545]"


def _card(agent_name: str) -> tuple[str, str, str]:
    """agentId/英文名 -> (卡片名, 图标, 职能)；未登记名原样返回。"""
    if agent_name == DEFAULT_AGENT:
        agent_name = "InvestmentAdvisorSupervisor"
    return AGENT_CARDS.get(agent_name, (agent_name, "🤖", ""))


def _slice_current_run(events: list[dict]) -> list[dict]:
    """切出最后一个 run_start 之后的轨迹片段（最近一次提问的执行过程）。"""
    last = -1
    for i, e in enumerate(events):
        if e.get("type") == "run_start":
            last = i
    return events[last:] if last >= 0 else list(events)


def _working_agents(run_events: list[dict]) -> list[str]:
    """由轨迹推断正在工作的 agent（供右上角指示）：最后一个事件非『输出』的 agent，
    加上最后一个事件所属 agent（若其最后事件不是输出）。"""
    if not run_events:
        return []
    last_type_by_agent: dict[str, str] = {}
    for e in run_events:
        if e.get("type") != "run_start" and e.get("agent"):
            last_type_by_agent[e["agent"]] = e["type"]
    working = [a for a, t in last_type_by_agent.items() if t in ("llm_call", "transfer")]
    last_agent = run_events[-1].get("agent")
    if last_agent and last_agent not in working and last_type_by_agent.get(last_agent) != "agent_text":
        working.append(last_agent)
    return working


def _render_chips(container: ui.column, events: list[dict]) -> None:
    """把轨迹事件渲染为 ZCode 风格的可折叠芯片（run_start 不展示）。"""
    for e in events:
        etype = e.get("type", "")
        if etype == "run_start":
            continue
        emoji = _EVENT_BADGES.get(etype, "•")
        dur = f" · {e.get('durationMs')}ms" if e.get("durationMs") is not None else ""
        card_name = _card(str(e.get("agent") or ""))[0]
        with container:
            if etype == "tool":
                args_text = json.dumps(e.get("args") or {}, ensure_ascii=False)
                result_text = str(e.get("result") or "")
                with ui.expansion(f"🔧 {e.get('name', '')}{dur}", caption=card_name) \
                        .props("dense").classes("w-full max-w-full bg-[#12161A] rounded"):
                    ui.label(f"入参：{args_text}").classes("text-xs text-grey-5 break-all")
                    ui.label(f"结果：{result_text[:300]}").classes("text-xs text-grey-5 break-all")
            elif etype == "transfer":
                target = _card(str(e.get("name") or ""))[0]
                ui.label(f"➡️ 转交 {target}").classes("text-xs text-amber-400")
            elif etype == "llm_call":
                ui.label(f"🧠 {card_name} 决策{dur} · {e.get('result') or ''}").classes("text-xs text-[#4A9EFF]")
            elif etype == "agent_text":
                ui.label(f"📤 {card_name} 输出结论").classes("text-xs text-[#00C08B]")


def _thinking_expanded(container: ui.column, events: list[dict], *, live: bool) -> None:
    """在 container 内渲染思考块：live=思考中（开、琥珀标题），否则收起为『已深度思考』。"""
    with container:
        if live:
            exp = ui.expansion("思考中…", icon="psychology") \
                .props("dense header-class=text-amber-400").classes("w-full")
            exp.open()  # 生成期间默认展开，实时芯片可见
            with exp:
                chips = ui.column().classes("w-full gap-1 p-1")
                with chips:
                    with ui.row().classes("items-center gap-2"):
                        ui.spinner("dots", size="sm", color="amber")
                        ui.label("正在拆解问题、调度管家…").classes("text-xs text-grey-5")
            container.chips = chips  # type: ignore[attr-defined]  # 供轮询追加
        else:
            n_steps = len([e for e in events if e.get("type") != "run_start"])
            exp = ui.expansion(f"已深度思考 · {n_steps} 步", icon="psychology") \
                .props("dense header-class=text-grey-5").classes("w-full")
            with exp:
                _render_chips(ui.column().classes("w-full gap-1 p-1"), events)


# ====================== 登录页 ======================

@ui.page("/login")
def login_page() -> None:
    ui.colors(primary="#E64545")
    with ui.card().classes("absolute-center w-96 p-8"):
        with ui.row().classes("w-full items-center justify-center gap-2"):
            ui.label("📈").classes("text-3xl")
            ui.label("量股化金").classes("text-2xl font-bold text-red-400")
            ui.label("AI 投顾终端").classes("text-sm text-grey-6 self-end pb-1")
        username = ui.input("用户名", placeholder="admin").classes("w-full")
        password = ui.input("密码", password=True, password_toggle_button=True).classes("w-full")

        async def do_login() -> None:
            ok, data = await run.io_bound(api_client.login, username.value.strip(), password.value)
            if ok:
                app.storage.user["token"] = data.get("token", "")
                app.storage.user["user"] = data
                ui.navigate.to("/")
            else:
                ui.notify(str(data), type="negative")

        ui.button("登 录", on_click=do_login).classes("w-full mt-2").props("unelevated size=lg")
        ui.label("演示管理员：admin / 123456").classes("text-xs text-grey-6 mt-1")


# ====================== 主页面 ======================

@ui.page("/")
def index() -> None:
    if not app.storage.user.get("token"):
        ui.navigate.to("/login")
        return

    ui.colors(primary="#E64545")
    user = app.storage.user.get("user") or {}
    uid = str(user.get("id", ""))
    team = api_client.agent_team(DEFAULT_AGENT) or {}

    # ---- 每连接状态（页面构建期闭包持有） ----
    st: dict = {
        "agent": DEFAULT_AGENT,      # 当前对话的 agentId（队长或专家）
        "session_id": None,          # 8091 内存会话 ID
        "running": False,            # 是否正在生成
        "last_seq": 0,               # 已渲染轨迹的最大 seq
        "chat_result": {},           # 后台 chat 线程结果 {'ok','answer','done'}
        "run_started_at": 0.0,
    }

    # ====================== 左侧固定栏 ======================

    def do_logout() -> None:
        app.storage.user.clear()
        ui.navigate.to("/login")

    drawer = ui.left_drawer(fixed=True, value=True).props("bordered width=290").classes("bg-[#12161A]")
    with drawer:
        with ui.column().classes("w-full h-full justify-between no-wrap"):
            # ---- 上部：品牌 / 新建对话 / 管家团队 / 知识库 / 历史 ----
            with ui.column().classes("w-full gap-1"):
                with ui.row().classes("w-full items-center gap-2 px-2 py-1"):
                    ui.label("📈").classes("text-2xl")
                    ui.label("量股化金").classes("text-lg font-bold text-red-400")
                    ui.label("AI 投顾终端").classes("text-[11px] text-grey-6")

                ui.button("新建对话", icon="add", on_click=lambda: start_new_chat()) \
                    .props("unelevated align=left").classes("w-full")

                # ---- 管家团队（可单独对话） ----
                team_exp = ui.expansion("管家团队", icon="groups").classes("w-full") \
                    .props("dense header-class=text-grey-4")
                with team_exp:
                    team_rows: dict[str, ui.row] = {}

                    def agent_row(agent_id: str) -> None:
                        card, icon, duty = _card(agent_id)
                        desc = "全局投顾 · 调度 6 位专家" if agent_id == DEFAULT_AGENT else duty
                        row = ui.row().classes(
                            "w-full items-center gap-2 px-2 py-1 rounded cursor-pointer hover:bg-[#1F262C]")
                        with row:
                            ui.label(icon).classes("text-lg")
                            with ui.column().classes("gap-0"):
                                ui.label(card).classes("text-sm font-medium")
                                ui.label(desc).classes("text-[10px] text-grey-6")
                        team_rows[agent_id] = row
                        row.on("click", lambda a=agent_id: chat_with(a))

                    agent_row(DEFAULT_AGENT)
                    for expert in (team.get("experts") or []):
                        agent_row(str(expert.get("name", "")))

                # ---- 知识库（上传 / 列表 / 删除） ----
                with ui.expansion("知识库", icon="folder_open").classes("w-full") \
                        .props("dense header-class=text-grey-4"):
                    kb_col = ui.column().classes("w-full gap-1 px-1")

                    async def handle_kb_upload(e) -> None:
                        ok, msg = await run.io_bound(api_client.kb_upload, uid, e.name, e.content)
                        ui.notify(msg, type="positive" if ok else "negative")
                        refresh_kb()

                    ui.upload(on_upload=handle_kb_upload, auto_upload=True, max_files=1) \
                        .props('accept=.txt,.md flat dense color=grey-6 label="上传 txt / md 文档"') \
                        .classes("w-full max-w-full")
                    ui.label("文档会注入对话上下文，可让投顾引用").classes("text-[10px] text-grey-6 px-1")

                # ---- 历史对话（可滑动） ----
                ui.label("历史对话").classes("text-xs text-grey-6 px-2 mt-1")
                history_scroll = ui.scroll_area().classes("w-full").style("max-height: 225px")
                history_col = ui.column().classes("w-full gap-1").style("min-width: 245px")

            # ---- 下部：账户卡片（固定左下角） ----
            with ui.column().classes("w-full"):
                with ui.card().classes("w-full bg-[#171C21]"):
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.icon("account_circle").classes("text-2xl text-grey-5")
                        with ui.column().classes("gap-0"):
                            ui.label(user.get("username", "")).classes("text-sm font-bold")
                            ui.label(user.get("identityDesc", "")).classes("text-[10px] text-grey-6")
                        ui.space()
                        ui.button(icon="logout", on_click=do_logout).props("flat round dense").tooltip("退出登录")
                ui.link("行情 / 交易终端 (Streamlit) →", "http://127.0.0.1:8501") \
                    .classes("text-[11px] text-grey-6 px-2")

    # ====================== 主区：对话 ======================

    with ui.column().classes("w-full h-full"):
        # ---- 顶栏：当前管家 + 右上角“正在工作”折叠指示 ----
        with ui.row().classes("w-full items-center justify-between px-6 py-2 border-b border-[#2A3138]"):
            with ui.row().classes("items-center gap-2"):
                header_icon = ui.label("👑")
                with ui.column().classes("gap-0"):
                    header_name = ui.label("队长").classes("text-base font-bold")
                    header_desc = ui.label("全局投顾 · 调度 6 位专家").classes("text-[11px] text-grey-6")
            # 右上角：正在工作的 Agent（可折叠菜单，参考 ZCode 运行指示）
            work_btn = ui.button("空闲", icon="psychology") \
                .props("flat dense no-caps size=sm color=grey-5").tooltip("正在工作的管家")
            with ui.menu().props("auto-close"):
                work_menu_col = ui.column().classes("p-2 gap-1 text-sm min-w-[12rem]")

        chat_scroll = ui.scroll_area().classes("w-full flex-grow")
        with chat_scroll:
            chat_col = ui.column().classes("w-full max-w-4xl mx-auto gap-3 p-4")

        # ---- 输入行 ----
        with ui.row().classes("w-full justify-center p-3 border-t border-[#2A3138] no-wrap items-center"):
            input_box = ui.input(placeholder="向 队长提问…") \
                .classes("w-[58rem]").props("outlined dense rounded")
            ui.button(icon="send", on_click=lambda: asyncio.create_task(send_message())) \
                .props("unelevated rounded size=lg").tooltip("发送")

        async def on_enter() -> None:
            await send_message()

        input_box.on("keydown.enter", on_enter)

    # ====================== 渲染辅助 ======================

    def render_user_bubble(text: str) -> None:
        with chat_col:
            with ui.row().classes("w-full justify-end"):
                with ui.card().classes("bg-[#3A1719] max-w-[75%]"):
                    ui.label(text).classes("text-sm whitespace-pre-wrap")

    def render_assistant_answer(text: str) -> None:
        with chat_col:
            with ui.row().classes("w-full"):
                with ui.card().classes("bg-[#171C21] max-w-[85%] w-full"):
                    ui.markdown(text)

    def update_header() -> None:
        card, icon, duty = _card(st["agent"])
        if st["agent"] == DEFAULT_AGENT:
            duty = "全局投顾 · 调度 6 位专家"
        header_icon.text = icon
        header_name.text = card
        header_desc.text = duty
        input_box.props(f'placeholder="向 {card}提问…"')

    def highlight_team() -> None:
        for aid, row in team_rows.items():
            row.classes(remove=_SEL_CLASS, add=_SEL_CLASS if aid == st["agent"] else "")

    def refresh_history() -> None:
        history_col.clear()
        rows = api_client.history_list(uid)
        with history_col:
            if not rows:
                ui.label("暂无历史对话").classes("text-[11px] text-grey-6 px-2")
            for srow in rows:
                aid = str(srow.get("agentId", ""))
                card, icon, _d = _card(aid)
                with ui.row().classes("w-full items-center gap-1 px-2 py-1 rounded cursor-pointer hover:bg-[#1F262C]") \
                        .on("click", lambda sid=str(srow.get("sessionId", "")), a=aid: open_history(sid, a)):
                    ui.label(icon).classes("text-sm")
                    with ui.column().classes("gap-0 flex-grow min-w-0"):
                        ui.label(srow.get("title", "新对话")).classes("text-xs truncate")
                        ui.label(f"{card} · {srow.get('updateTime', '')}").classes("text-[10px] text-grey-6")
                    ui.button(icon="delete", on_click=lambda sid=str(srow.get("sessionId", "")): delete_history(sid)) \
                        .props("flat round dense size=xs color=grey-7")

    def delete_history(sid: str) -> None:
        api_client.history_delete(sid, uid)
        if st.get("session_id") == sid:
            st["session_id"] = None
        refresh_history()
        ui.notify("已删除该会话", type="info")

    def refresh_kb() -> None:
        kb_col.clear()
        docs = api_client.kb_list(uid)
        with kb_col:
            if not docs:
                ui.label("暂无文档，上传后投顾可检索引用").classes("text-[11px] text-grey-6")
            for d in docs:
                with ui.row().classes("w-full items-center gap-1 px-2 py-1 rounded hover:bg-[#1F262C]"):
                    ui.icon("description").classes("text-sm text-grey-5")
                    with ui.column().classes("gap-0 flex-grow min-w-0"):
                        ui.label(str(d.get("title", ""))).classes("text-xs truncate")
                        ui.label(f"{d.get('charCount', 0)} 字 · {d.get('createTime', '')}").classes("text-[10px] text-grey-6")
                    ui.button(icon="close", on_click=lambda did=int(d.get("id", 0)): kb_remove(did)) \
                        .props("flat round dense size=xs color=grey-7")

    def kb_remove(did: int) -> None:
        api_client.kb_delete(did, uid)
        refresh_kb()
        ui.notify("已从知识库移除", type="info")

    # ====================== 状态流转 ======================

    def start_new_chat() -> None:
        """新建对话：主区默认态（队长，未选定具体会话）。"""
        st["agent"] = DEFAULT_AGENT
        st["session_id"] = None
        st["last_seq"] = 0
        st["running"] = False
        st["chat_result"] = {}
        chat_col.clear()
        with chat_col:
            with ui.column().classes("w-full items-center py-16 gap-2"):
                ui.label("👑").classes("text-5xl")
                ui.label("新建对话").classes("text-lg font-bold")
                ui.label("从左侧「管家团队」选择任意管家单独对话，或直接向队长提问（自动调度专家）。").classes("text-xs text-grey-6")
        update_header()
        highlight_team()

    def chat_with(agent_id: str) -> None:
        """点击左侧管家：与该管家开一个新对话。"""
        st["agent"] = agent_id
        st["session_id"] = None
        st["last_seq"] = 0
        st["running"] = False
        st["chat_result"] = {}
        chat_col.clear()
        card, icon, duty = _card(agent_id)
        with chat_col:
            with ui.column().classes("w-full items-center py-16 gap-2"):
                ui.label(icon).classes("text-5xl")
                ui.label(card).classes("text-lg font-bold")
                ui.label(duty).classes("text-xs text-grey-6")
        update_header()
        highlight_team()

    def open_history(sid: str, agent_id: str) -> None:
        """查看历史会话（可继续在该会话中提问）。"""
        st["agent"] = agent_id
        st["session_id"] = sid
        st["last_seq"] = 0
        st["running"] = False
        st["chat_result"] = {}
        chat_col.clear()
        messages = api_client.history_messages(sid)
        with chat_col:
            if not messages:
                ui.label("该会话暂无消息").classes("text-xs text-grey-6")
            for m in messages:
                if m.get("role") == "user":
                    render_user_bubble(m.get("content", ""))
                else:
                    trace = m.get("trace") or []
                    if trace:
                        wrapper = ui.column().classes("w-full")
                        _thinking_expanded(wrapper, trace, live=False)
                    render_assistant_answer(m.get("content", ""))
        update_header()
        highlight_team()
        chat_scroll.scroll_to(percent=1.0)

    # ====================== 发送与实时思考 ======================

    async def send_message() -> None:
        if st["running"] or not input_box.value.strip():
            return
        text = input_box.value.strip()
        input_box.value = ""
        st["running"] = True
        st["chat_result"] = {}
        st["last_seq"] = 0
        st["run_started_at"] = time.time()

        # 首次提问先建会话（同 (agent, user) 幂等）
        if not st["session_id"]:
            chat_col.clear()
            st["session_id"] = await run.io_bound(api_client.create_session, st["agent"], uid)
            if not st["session_id"]:
                st["running"] = False
                render_assistant_answer("创建会话失败：智能体服务（8091）不可用。")
                return

        render_user_bubble(text)
        with chat_col:  # 思考块必须挂在消息流内，收尾时才能定位替换
            thinking_wrap = ui.column().classes("w-full")
        _thinking_expanded(thinking_wrap, [], live=True)
        chat_scroll.scroll_to(percent=1.0)

        async def worker() -> None:
            ok, answer = await run.io_bound(api_client.chat, st["agent"], uid, st["session_id"], text)
            st["chat_result"] = {"ok": ok, "answer": answer, "done": True}

        asyncio.create_task(worker())

    async def poll_trace() -> None:
        """生成期间轮询轨迹：追加思考芯片 + 更新右上角工作指示 + 收尾渲染回答。"""
        if not st["running"]:
            return
        events = await run.io_bound(api_client.trace, st["agent"], uid, st["session_id"] or "")
        run_events = _slice_current_run(events)
        new_events = [e for e in run_events if isinstance(e.get("seq"), int) and e["seq"] > st["last_seq"]]

        # 追加思考芯片（首轮事件到达时清掉占位 spinner）
        if new_events:
            chips: ui.column | None = getattr(chat_col, "_live_chips", None)
            if chips is None:
                exps = [el for el in chat_col if hasattr(el, "chips")]
                chips = exps[-1].chips if exps else None  # type: ignore[attr-defined]
            if chips is not None:
                firsts = [e for e in new_events if e.get("type") != "run_start"]
                if firsts and not getattr(chat_col, "_live_started", False):
                    chat_col._live_started = True  # type: ignore[attr-defined]
                    chips.clear()
                _render_chips(chips, firsts)
            st["last_seq"] = max(int(e["seq"]) for e in new_events)
            chat_scroll.scroll_to(percent=1.0)

        # 右上角“正在工作”指示
        working = _working_agents(run_events)
        if working:
            work_btn.text = f"{len(working)} 位管家工作中"
            work_btn.props("color=amber-400")
        else:
            work_btn.text = "思考中…"
            work_btn.props("color=grey-5")
        work_menu_col.clear()
        with work_menu_col:
            if working:
                for aid in working:
                    card, icon, _d = _card(aid)
                    with ui.row().classes("items-center gap-2"):
                        ui.label(f"{icon} {card}").classes("text-sm")
                        ui.badge("工作中", color="amber-10")
            else:
                ui.label("当前没有正在工作的管家").classes("text-xs text-grey-6")

        # 后台 chat 完成 → 收尾
        if st["chat_result"].get("done"):
            await finalize_answer(run_events)

    async def finalize_answer(run_events: list[dict]) -> None:
        st["running"] = False
        result = st["chat_result"]
        chat_col._live_started = False  # type: ignore[attr-defined]
        work_btn.text = "空闲"
        work_btn.props("color=grey-5")

        # 把“思考中”块替换为收起的『已深度思考』块
        last_cards = [el for el in chat_col if isinstance(el, ui.column)]
        if last_cards:
            wrapper = last_cards[-1]
            wrapper.clear()
            _thinking_expanded(wrapper, run_events, live=False)

        answer = result.get("answer") or ("智能体暂不可用，请稍后重试。" if not result.get("ok") else "")
        if answer:
            render_assistant_answer(answer)
        chat_scroll.scroll_to(percent=1.0)
        refresh_history()

    # 实时轮询（空闲时空转开销极小）
    ui.timer(0.8, poll_trace)

    # ====================== 初始化 ======================

    try:
        team_exp.open()  # 管家团队默认展开
    except Exception:  # noqa: BLE001 旧版 API 兼容
        pass
    refresh_history()
    refresh_kb()
    start_new_chat()


ui.run(
    host="127.0.0.1",
    port=8502,
    title="量股化金 · AI 投顾终端",
    dark=True,
    reload=False,
    show=False,
    favicon="📈",
    storage_secret="lghj-agent-web-secret",
)
