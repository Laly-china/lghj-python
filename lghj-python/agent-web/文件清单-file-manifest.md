# 文件清单-file-manifest（agent-web/ AI 投顾终端）

参考腾讯 Marvis「AI 管家」界面结构用 NiceGUI（纯 Python）实现的 AI 投顾终端，
端口 8502；与 streamlit-web（交易终端，8501）并存互补。

## 文件

| 文件 | 说明 |
| --- | --- |
| `main.py` | 入口：`/login` 登录页（走 8080 /api/login）+ `/` 主页面。左栏：品牌 / 新建对话 / 管家团队（7 个 Agent 可单独对话，点击即切换）/ 知识库（上传 txt/md、删除）/ 历史对话（可滑动，点击回看与续聊）/ 底部固定账户卡片；主区：当前管家头栏 + 右上角「正在工作」可折叠指示 + 消息流（发问后实时渲染思考芯片：LLM 决策 / 工具调用 / 转交，参考 ZCode 折叠芯片；回答 Markdown）+ 输入行。实时机制：后台线程执行 8091 阻塞 chat，0.8s 定时轮询 /api/v1/trace 增量追加芯片 |
| `api_client.py` | 三后端 HTTP 客户端：8080 登录；8091 chat / trace / agent_team / history_* / kb_*（全部失败降级返回安全默认值） |
| `启动投顾终端-run-agent-web.bat` | 一键启动（venv 相对路径） |

## 依赖的 8091 扩展接口（原 Java 无）

- `GET /api/v1/trace`（执行轨迹）、`GET /api/v1/agent_team`（团队结构）
- `GET /api/v1/history_list`、`GET /api/v1/history_messages`、`DELETE /api/v1/history_session`
- `POST /api/v1/kb_upload`、`GET /api/v1/kb_list`、`DELETE /api/v1/kb_doc`
- 专家智能体（MarketAnalysisAgent 等 6 个）已注册为可独立对话 agent，
  `create_session(agentId=专家名)` 即可单独会话

## 依赖

- venv 需安装 nicegui（`pip install nicegui`）
- MySQL（127.0.0.1:3306 lghj 库）：历史与知识库持久化表 agent_chat_session /
  agent_chat_message / agent_kb_doc（由 8091 启动时幂等建表）
