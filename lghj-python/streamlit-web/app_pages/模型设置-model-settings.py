# -*- coding: utf-8 -*-
"""模型设置页 —— cc-switch 风格多模型选择（用户自配多个 OpenAI 兼容提供商并一键切换）

- 配置存主服务 8080（本地 MySQL，api_key 不回显明文，接口打码）
- 选中的配置在 AI 投顾聊天时生效（8091 按用户路由）；未配置/未激活走系统默认
"""

import streamlit as st

import api
import components as ui

st.header("模型设置", icon=":material/psychology:")

ui.require_login()

# ---------------- 云端提供商预设（选预设自动填地址/模型名，key 自己填） ----------------
PRESETS: dict[str, dict[str, str]] = {
    "DeepSeek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "completions_path": "/v1/chat/completions",
        "hint": "DeepSeek 官方 OpenAI 兼容接口",
    },
    "通义千问 DashScope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-flash",
        "completions_path": "/chat/completions",
        "hint": "阿里云百炼 DashScope 兼容模式",
    },
    "月之暗面 Kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "completions_path": "/chat/completions",
        "hint": "Kimi OpenAI 兼容接口",
    },
    "智谱 GLM": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "completions_path": "/chat/completions",
        "hint": "智谱开放平台",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "completions_path": "/chat/completions",
        "hint": "OpenAI 官方接口",
    },
    "自定义": {
        "base_url": "",
        "model": "",
        "completions_path": "/chat/completions",
        "hint": "任意 OpenAI 兼容接口（ollama/vLLM/one-api 等）",
    },
}

configs = api.model_config_list()
active = next((c for c in configs if c.get("isActive")), None)

# ---------------- 当前使用状态 ----------------
with st.container(border=True):
    if active:
        st.markdown(
            f"**当前使用：{active.get('name', '')}**　"
            f"<span style='font-size:12px;color:#6B7480'>{active.get('model', '')}</span>",
            unsafe_allow_html=True,
        )
        st.caption("AI 投顾将使用该模型回答（切换后最迟 20 秒生效）")
    else:
        st.markdown("**当前使用：系统默认**　<span style='font-size:12px;color:#6B7480'>deepseek-chat</span>",
                    unsafe_allow_html=True)
        st.caption("未选择自定义模型时，AI 投顾使用服务端默认配置（DeepSeek）")

# ---------------- 新增 / 修改配置 ----------------
st.subheader("添加配置", anchor=False)

preset = st.selectbox("提供商预设", list(PRESETS.keys()), key="mc_preset",
                      help="选预设自动填地址与模型名，只需填入你的 API Key")
if st.session_state.get("mc_preset_prev") != preset:
    # 切换预设：清掉表单控件的旧值，让新预设默认值生效
    st.session_state.mc_preset_prev = preset
    for k in ("mc_name", "mc_key", "mc_model", "mc_base", "mc_path",
              "mc_models", "mc_model_pick"):
        st.session_state.pop(k, None)
    p = PRESETS[preset]
    st.session_state.mc_name = "" if preset == "自定义" else preset
    st.session_state.mc_base = p["base_url"]
    st.session_state.mc_model = p["model"]
    st.session_state.mc_path = p["completions_path"]
    st.rerun()

# 保存成功后的下一次渲染：在控件实例化前清掉明文 key
if st.session_state.pop("mc_clear_key", False):
    st.session_state.pop("mc_key", None)

with st.container(border=True):
    st.text_input("配置名称（保存后可用于切换）", key="mc_name",
                  help="如：DeepSeek主力 / 千问备用。同名保存会覆盖旧配置")
    st.text_input("API Key", key="mc_key", type="password",
                  help="仅保存在服务器本地数据库，页面只显示打码后的形式")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.text_input("接口地址 Base URL", key="mc_base")
    with c2:
        st.text_input("补全路径", key="mc_path",
                      help="地址已含 /v1 等版本段时用 /chat/completions；"
                           "裸域名（如 DeepSeek）用 /v1/chat/completions")

    # ---- 模型名：支持从厂商实时拉取列表选择（跟随厂商上下架，无需手填猜测）----
    mcol1, mcol2 = st.columns([3, 1.2])
    with mcol1:
        st.text_input("模型名", key="mc_model")
    with mcol2:
        st.write("")  # 对齐占位
        if st.button("拉取模型列表", icon=":material/refresh:", use_container_width=True,
                     help="用上面填的地址和 Key 调厂商 /models 接口，拉取当前可用模型"):
            ok, result = api.fetch_vendor_models(
                st.session_state.get("mc_base") or "",
                st.session_state.get("mc_key") or "",
                st.session_state.get("mc_path") or "",
            )
            if ok:
                st.session_state.mc_models = result
                st.toast(f"拉到 {len(result)} 个模型", icon=":material/check_circle:")
            else:
                st.session_state.pop("mc_models", None)
                st.error(result)
    models = st.session_state.get("mc_models") or []
    if models:
        st.selectbox(
            "从列表选择（自动填入模型名）",
            models,
            index=None,
            key="mc_model_pick",
            on_change=lambda: setattr(
                st.session_state, "mc_model", st.session_state.get("mc_model_pick") or ""
            ),
        )
    st.caption(PRESETS[preset]["hint"])

    if st.button("保存配置", type="primary", use_container_width=True):
        name = (st.session_state.get("mc_name") or "").strip()
        key_val = (st.session_state.get("mc_key") or "").strip()
        base = (st.session_state.get("mc_base") or "").strip()
        model = (st.session_state.get("mc_model") or "").strip()
        path = (st.session_state.get("mc_path") or "").strip()
        if not (name and key_val and base and model):
            st.error("配置名称 / API Key / 接口地址 / 模型名 均不能为空")
        else:
            ok, msg = api.model_config_save(name, base, key_val, model, path)
            if ok:
                st.toast("配置已保存", icon=":material/check_circle:")
                # 打标记，下次渲染前清掉明文 key 与拉取的列表
                st.session_state.mc_clear_key = True
                st.session_state.pop("mc_models", None)
                st.rerun()
            else:
                st.error(msg)

# ---------------- 我的配置列表 ----------------
st.subheader("我的配置", anchor=False)
if not configs:
    st.caption("还没有配置。添加并「设为当前」后，AI 投顾将使用你自己的模型。")
for c in configs:
    is_on = bool(c.get("isActive"))
    with st.container(border=True):
        left, right = st.columns([3.2, 1.4])
        with left:
            st.markdown(
                f"**{c.get('name', '')}**　"
                f"<span style='font-size:12px;color:{'#E64545' if is_on else '#6B7480'}'>"
                f"{'● 使用中' if is_on else '○ 未启用'}</span>",
                unsafe_allow_html=True,
            )
            st.caption(f"{c.get('model', '')}　·　`{c.get('baseUrl', '')}`")
            st.caption(f"Key：{c.get('apiKey', '****')}")
        with right:
            if is_on:
                st.button("使用中", disabled=True, use_container_width=True,
                          key=f"mc_on_{c.get('id')}", icon=":material/check_circle:")
            else:
                if st.button("设为当前", type="primary", use_container_width=True,
                             key=f"mc_act_{c.get('id')}"):
                    ok, msg = api.model_config_activate(str(c.get("name", "")))
                    if ok:
                        st.toast("已切换模型", icon=":material/swap_horiz:")
                        st.rerun()
                    else:
                        st.error(msg)
            if st.button("删除", use_container_width=True, key=f"mc_del_{c.get('id')}"):
                ok, msg = api.model_config_delete(str(c.get("name", "")))
                if ok:
                    st.toast("已删除", icon=":material/delete:")
                    st.rerun()
                else:
                    st.error(msg)

st.divider()
st.caption("隐私说明：API Key 只保存在本系统服务器数据库中，页面上永远只显示打码形式；"
           "对话内容仅发送给你所选的模型提供商。")
