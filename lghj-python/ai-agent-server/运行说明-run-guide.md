# 运行说明 - Run Guide

「量股化金」Phase 5：AI 智能体投顾服务（ai-agent-server，端口 8091，DDD 复现）

## 1. 启动

```bash
# 解释器用共享 venv，不要 activate
# 项目根 = env/ 与 lghj-python/ 的上一级；以下相对路径在 ai-agent-server 目录内执行
cd lghj-python/ai-agent-server
"../../env/venv-虚拟环境/Scripts/python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8091

# 或直接运行入口
"../../env/venv-虚拟环境/Scripts/python.exe" app/main.py
```

应用启动（lifespan）时自动执行智能体装配：加载
`app/resources/agent/投顾装配-investment-advisor-supervisor.yml` →
AiApi → ChatModel（挂载本地工具 + skills）→ 6 专家 Agent → Supervisor 层级编排 → Runner，
注册 agentId=`investment-advisor`。

## 2. 环境变量（照抄原 Java application-dev.yml 占位符）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 空 | LLM Key（任务指定，优先）；为空时回落 `AI_AGENT_API_KEY` |
| `AI_AGENT_API_KEY` | 空 | 原 Java 工程的 Key 变量（回落用） |
| `AI_AGENT_BASE_URL` | https://api.deepseek.com | LLM base-url（yml 占位） |
| `AI_AGENT_MODEL` | deepseek-chat | 模型名（yml 占位） |
| `LGHJ_BASE_URL` | http://127.0.0.1:8080 | 主服务地址 |
| `LGHJ_INTERNAL_API_TOKEN` | 空 | 内部接口令牌（`X-Internal-Token` 头的值） |
| `LGHJ_CLIENT_TIMEOUT_SECONDS` | 5 | 调主服务超时秒数 |
| `AGENT_CONFIG_LOCAL_ENABLED` | false | 是否加载本地覆写装配（调试实验配置，默认关） |

**无 DEEPSEEK_API_KEY 时**：装配/参数校验/会话管理/错误路径全部可用；
chat/chat_stream 在 LLM 调用阶段失败，接口返回 `Response{code:"0001", info:"未知失败"}`。
本地工具（queryRealtimeMarket/querySimTradeProfile）不依赖 LLM Key，主服务 8080 未就绪时
返回原 Java 定义的失败文案（`未获取到实时行情…` / `未获取到模拟交易画像…`）。

## 3. 自测记录（2026-10-02）

| 用例 | 结果 |
| --- | --- |
| `from app.main import app` 导入检查 | 通过 |
| GET `/act/health` | `{"status":"UP"}` |
| GET `/api/v1/query_ai_agent_config_list` | `{"code":"0000",...data:[{agentId:"investment-advisor", agentName:"智能投资顾问", agentDesc:"基于多智能体层级编排的股票投资咨询助手"}]}` |
| POST / GET `/api/v1/create_session`（同 userId） | 均返回同一 sessionId（会话复用，对齐原 Java computeIfAbsent） |
| create_session 未知 agentId | `{"code":"E0001","info":"智能体ID不存在"}` |
| POST `/api/v1/chat`（无 sessionId） | 自动建会话；DeepSeek 真实返回，supervisor 直答，输出七段式结构，系统上下文 userId 注入生效 |
| POST `/api/v1/chat`（行情问题） | supervisor 转交专家 → queryRealtimeMarket → 8080 未就绪 → 工具返回 `{"success":false,"message":"未获取到实时行情，可能是行情源、主后端或股票代码不可用。"}`（原 Java 文案照抄），模型明确说明数据缺口 |
| POST `/api/v1/chat`（画像问题，mock 8080） | supervisor 转交 PersonalTradeProfileAgent → querySimTradeProfile → mock 收到 `GET /api/internal/sim-trade/profile?userId=u2002` |
| 内部端口请求契约（直连 mock 断言） | URL/参数/`X-Internal-Token` 完全对齐：`/api/internal/market/realtime?market=sh&code=600519&recentNewsSize=5&includeMinute=True`；token 环境变量非空时携带、为空时不带 |
| POST `/api/v1/chat_stream` | HTTP 200，`content-type: text/plain; charset=utf-8`，chunked，事件文本原样写响应体（无 `data:` 前缀，对齐 ResponseBodyEmitter） |
| 参数校验（缺 body / 缺 Query 参数 / 类型错误） | HTTP 422（FastAPI 默认；原 Spring 为 400，见偏差说明） |
| 自测后进程清理 | 已杀掉 uvicorn 与 mock 8080 |

## 4. 已知偏差（相对原 Java）

1. **google-adk → 手写运行时**：原 Java 用 google-adk-java（InMemoryRunner/AutoFlow）+ Spring AI。
   为避免 google-adk-python 与共享 venv 的 fastapi/pydantic 版本冲突，按 ADK 语义手写了等价
   最小运行时（会话/事件/transfer_to_agent 编排/工具循环），对外 HTTP 契约不受影响。
2. **事件粒度**：原 Java 每次模型响应产生一个 Event（非流式模式），本实现一致；
   chat_stream 响应体为各事件文本原样拼接（无分隔符）。
3. **并行工作流**：ParallelAgent 原为并发执行，本实现按顺序执行以保证会话消息顺序一致
   （主装配仅用 supervisor，不影响现网行为）。
4. **参数校验状态码**：Spring 缺参返回 400，FastAPI 返回 422（响应体为框架默认格式）。
5. **chat_stream 前置失败**：原 Java 建会话失败时 emitter.completeWithError（HTTP 500）；
   本实现建立流之前校验，失败返回统一 Response 错误体（HTTP 200），与其余接口契约一致。
6. **LoopAgentNode 路由修正**：原 Java `getBean("agentWorkflow")` 为错误 bean 名（用到 loop
   时会运行时失败）；本实现回环到工作流路由节点。
7. **本地覆写装配默认关闭**：原 Java optional import 的 local yml 会按 Spring 列表覆盖语义
   替换 agent-workflows（导致 Supervisor 失去 sub-agents），属调试实验配置；本服务默认不加载，
   环境变量 `AGENT_CONFIG_LOCAL_ENABLED=true` 可开启复现该行为。
8. **安全**：原仓库 local yml 内含明文 DeepSeek api-key，本复现不落盘任何密钥，统一走环境变量。
9. **多模态**：ChatCommandEntity 的文件/内联数据部件在文本模型（DeepSeek）下以文本占位符
   传入（原 Java 用 Gemini 式 Part.fromUri/fromBytes）。
10. **plugins**：原 Java runner 可挂 ADK 插件（myTestPlugin/myLogPlugin，日志职责），
    本实现以标准 logging 承接，不解析 pluginNameList。
11. **SSE/stdio MCP**：原 Java ChatModelNode 支持 sse/stdio 型 MCP 客户端；主装配仅用 local，
    本实现只实现 local（sse/stdio 配置会告警跳过，对应 E0002 语义记录日志）。
