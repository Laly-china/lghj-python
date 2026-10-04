# 文件清单 - File Manifest

「量股化金」Phase 5：AI 智能体投顾服务（ai-agent-server，端口 8091）
Java→Python DDD 复现。原 Java 工程：`lghj-web-dist.tar/ai-agent-scaffoid-feng/`（Maven 多模块）。

命名约定：**不被 Python import 的文件**（md/yml/txt）一律中文-english 双语命名；
**必须被 import 的源码文件/包目录**保留英文名（import 机制限制），每个英文文件在下方配中文说明。

---

## 1. 交付根目录

| 文件 | 说明 |
| --- | --- |
| `文件清单-file-manifest.md` | 本清单 |
| `依赖清单-requirements-ai-agent.txt` | Python 依赖清单（共享 venv 已全部预装，仅作固化） |
| `运行说明-run-guide.md` | 启动方式、环境变量、自测记录 |

## 2. app/ 应用包

| 文件 | 对应原 Java | 说明 |
| --- | --- | --- |
| `app/__init__.py` | - | 应用包标识 |
| `app/main.py` | `-app` 模块 `cn/feng/Application.java` + `config/AiAgentAutoConfig.java` | FastAPI 入口：组装端口/工厂/服务，应用就绪后执行智能体装配（lifespan），挂载 4 个路由，健康检查 `/act/health` |
| `app/config.py` | `LghjClientProperties.java` + `application-dev.yml` | 配置：端口 8091、lghj.client（LGHJ_BASE_URL/LGHJ_INTERNAL_API_TOKEN/LGHJ_CLIENT_TIMEOUT_SECONDS）、LLM Key（DEEPSEEK_API_KEY 优先，回落 AI_AGENT_API_KEY）、装配文件路径；**扩展（原 Java 无）**：MySQL 连接（扩展存储 agent_* 表用） |

## 2b. app/infrastructure/ 扩展存储（本工程新增，原 Java 无）

| 文件 | 对应原 Java | 说明 |
| --- | --- | --- |
| `app/infrastructure/database.py` | - | 扩展存储引擎（复用主控 MySQL lghj 库）：懒加载 engine + session_tx 事务上下文 + 启动幂等建表（agent_chat_session / agent_chat_message / agent_kb_doc，DDL 见 sql/智能体扩展表-agent-extension.sql） |
| `app/infrastructure/chat_store.py` | - | 会话历史 CRUD（record_turn 每轮落库/列表/消息/删除）与个人知识库 CRUD + 关键词检索（段落计分）；DbKbSearchPort 实现 KbSearchPort 供本地工具检索 |

## 3. app/types/ 类型层（对应 `-types` 模块）

| 文件 | 对应原 Java | 说明 |
| --- | --- | --- |
| `app/types/__init__.py` | - | 包标识 |
| `app/types/constants.py` | `types/common/Constants.java` | 常量 SPLIT="," |
| `app/types/response_code.py` | `types/enums/ResponseCode.java` | 响应码：0000 成功 / 0001 未知失败 / 0002 非法参数 / 0003 不存在的方法 / E0001 智能体ID不存在 / E0002 智能体MCP配置不在可加载范围 |
| `app/types/app_exception.py` | `types/exception/AppException.java` | 应用异常（code+info），trigger 层统一捕获 |

## 4. app/api/ 契约层（对应 `-api` 模块）

| 文件 | 对应原 Java | 说明 |
| --- | --- | --- |
| `app/api/__init__.py` | - | 包标识 |
| `app/api/response.py` | `api/response/Response.java` | 统一响应体 `Response{code, info, data}` |
| `app/api/dto.py` | `api/dto/*.java`（5 个 DTO） | ChatRequestDTO / ChatResponseDTO / CreateSessionRequestDTO / CreateSessionResponseDTO / AiAgentConfigResponseDTO，字段名照抄 |

## 5. app/domain/agent/ 领域层（对应 `-domain` 模块）

| 文件 | 对应原 Java | 说明 |
| --- | --- | --- |
| `domain/agent/adapter/port.py` | `adapter/port/MarketDataPort.java`、`SimTradeProfilePort.java` | 领域出端口接口（行情/画像） |
| `domain/agent/adapter/model/valobj.py` | `model/valobj/AiAgentConfigTableVO.java`、`AiAgentRegisterVO.java`、`enums/AgentTypeEnum.java`、`properties/AiAgentAutoConfigProperties.java` | 值对象：配置表/注册表/装配类型枚举/装配属性 |
| `domain/agent/adapter/model/entity.py` | `model/entity/ArmoryCommandEntity.java`、`ChatCommandEntity.java` | 实体：装配命令、多模态对话命令 |
| `domain/agent/service/chat_service.py` | `service/chat/ChatService.java`、`IChatService.java` | 对话服务：阻塞/流式消息、交易画像注入（仅 investment-advisor，上限 6000 字符超长加 `...[truncated]`）；create_session **每次新建会话**（原 Java 同用户复用同一 sessionId；本工程扩展历史落库后改为每次新建，否则多轮「新建对话」都折进同一历史行且上下文无法隔离；前端单次页面会话内仍复用 advisor_session）；**扩展（原 Java 无）**：get_trace 查询会话执行轨迹、get_team 查询团队结构（Supervisor+专家职能+工具名），供 Agent 流程可视化 |
| `domain/agent/service/armory/armory_service.py` | `service/IArmoryService.java`、`armory/ArmoryService.java` | 装配服务：遍历配置表驱动装配树 |
| `domain/agent/service/armory/factory.py` | `armory/factory/DefaultArmoryFactory.java` | 装配工厂 + DynamicContext + 智能体注册表（原 Java 用 Spring 容器，此处线程安全字典） |
| `domain/agent/service/armory/nodes.py` | `armory/node/RootNode/AiApiNode/ChatModelNode/AgentNode/AgentWorkflowNode/RunnerNode.java` 及 `node/workflow/*`（4 个工作流节点） | 装配树：Root→AiApi→ChatModel→Agent→AgentWorkflow→Runner，路由 loop/parallel/sequential/supervisor |
| `domain/agent/service/armory/runtime.py` | `com.google.adk`（Event/Content/Part/Session/InMemoryRunner/BaseAgent/LlmAgent/LoopAgent/ParallelAgent/SequentialAgent） | ADK 语义的轻量运行时：会话服务、事件流、transfer_to_agent 层级编排、工具调用循环（MAX_TOOL_ROUNDS=10）；**扩展（原 Java 无）**：会话 trace 打点（run_start/llm_call/transfer/tool/agent_text，含耗时与结果摘要），只记录不影响对话行为 |
| `domain/agent/service/armory/model_client.py` | `AiApiNode`（OpenAiApi）+ `ChatModelNode`（OpenAiChatModel）+ `AgentNode`（SpringAI 适配器） | litellm 客户端（OpenAI 兼容协议调 DeepSeek），api_base 由 base-url + completions-path 推导 |
| `domain/agent/service/matter/local_tools.py` | `armory/matter/mcp/server/InvestmentTradeProfileMcpService.java`、`MarketRealtimeMcpService.java`、`InvestmentTradeProfileMcpServerConfig.java` | 本地工具：querySimTradeProfile / queryRealtimeMarket，工具描述、参数说明、错误文案照抄原 Java 注解；注册表 bean 名 investmentTradeProfileMcp / marketRealtimeMcp |

## 6. app/infrastructure/ 基础设施层（对应 `-infrastructure` 模块 + `-app` 模块端口实现）

| 文件 | 对应原 Java | 说明 |
| --- | --- | --- |
| `infrastructure/adapter/http_ports.py` | `-app` 模块 `cn/feng/adapter/port/HttpMarketDataPort.java`、`HttpSimTradeProfilePort.java`、`config/LghjClientProperties.java` | httpx 实现：GET `/api/internal/market/realtime?market&code&recentNewsSize&includeMinute`、GET `/api/internal/sim-trade/profile?userId`，token 非空时带头 `X-Internal-Token`，任何异常降级返回 "" |

> 原 `-infrastructure` 模块只有 package-info 占位（无实现类），HTTP 实现位于 `-app` 模块，故此处与 `-app` 对应。

## 7. app/trigger/ 触发层（对应 `-trigger` 模块）

| 文件 | 对应原 Java | 说明 |
| --- | --- | --- |
| `trigger/http/agent_controller.py` | `trigger/http/AgentServiceController.java`、`api/IAgentService.java` | 4 个对外接口（GET query_ai_agent_config_list；GET/POST create_session；POST chat；POST chat_stream），统一 Response 契约、AppException/UN_ERROR 兜底、StreamingResponse 流式（对齐 ResponseBodyEmitter 原样写文本流语义）；**扩展（原 Java 无）**：GET /api/v1/trace（会话执行轨迹）、GET /api/v1/agent_team（团队结构），供前端 Agent 流程可视化 |

## 8. app/resources/agent/ 资源（双语命名，代码按实际文件名读取）

| 文件 | 对应原文件 | 说明 |
| --- | --- | --- |
| `投顾装配-investment-advisor-supervisor.yml` | `agent/investment_advisor_supervisor.yml` | 主装配：6 专家 Agent（MarketAnalysis/QuantTechnical/PersonalTradeProfile/RiskAssessment/PortfolioAdvice/ComplianceDisclosure）+ InvestmentAdvisorSupervisor 层级编排，instruction 七段式文本原文照抄；支持 `${VAR:default}` 环境占位 |
| `投顾本地覆写-investment-advisor-supervisor-local.yml` | `agent/investment_advisor_supervisor_local.yml` | 本地可选覆写（问候语处理实验配置）；默认不加载（AGENT_CONFIG_LOCAL_ENABLED=true 开启）；原文件内含明文 api-key，出于安全未照抄，改为环境变量占位 |
| `skills/investment-research/投研技能-investment-research-SKILL.md` | `agent/skills/investment-research/SKILL.md` | 投研技能说明（照抄），经 load_skill 工具加载（对应原 Java SkillsTool） |

## 9. 对外接口契约（照抄原 Java）

| 方法 路径 | 请求 | 响应 |
| --- | --- | --- |
| GET `/api/v1/query_ai_agent_config_list` | - | `Response{code:"0000", info:"成功", data:[{agentId, agentName, agentDesc}]}` |
| GET `/api/v1/create_session?agentId&userId` | Query 参数 | `Response{..., data:{sessionId}}` |
| POST `/api/v1/create_session` | `{agentId, userId}` | 同上 |
| POST `/api/v1/chat` | `{agentId, userId, sessionId, message}`（sessionId 空则自动建会话） | `Response{..., data:{content}}`（各事件文本按 `\n` 连接） |
| POST `/api/v1/chat_stream` | 同 chat | HTTP 200，`text/plain; charset=utf-8`，chunked；事件文本原样写入响应体（无 `data:` SSE 前缀，对齐 ResponseBodyEmitter） |

**扩展接口（本工程新增，原 Java 无——Agent 流程可视化 + 历史 + 知识库）：**

| 方法 路径 | 请求 | 响应 |
| --- | --- | --- |
| GET `/api/v1/trace?agentId&userId&sessionId` | Query 参数 | `Response{code:"0000", data:[{seq,ts,type,agent,name,args,result,durationMs}]}`；type=run_start/llm_call/transfer/tool/agent_text，按发生顺序；会话不存在返回空列表 |
| GET `/api/v1/agent_team?agentId` | Query 参数 | `Response{..., data:{agentId, supervisor:{name,description}, experts:[{name,description,outputKey}], tools:[工具名]}}`（管家卡片职能说明的数据源） |
| GET `/api/v1/history_list?userId&limit` | Query 参数 | `Response{..., data:[{sessionId,agentId,title,updateTime}]}`（MySQL 持久化，最近活跃倒序） |
| GET `/api/v1/history_messages?sessionId` | Query 参数 | `Response{..., data:[{role,content,createTime}]}`（assistant 附 trace 数组） |
| DELETE `/api/v1/history_session?sessionId&userId` | Query 参数 | `Response{..., data:{deleted}}`（按归属校验后物理删除） |
| POST `/api/v1/kb_upload` | multipart：userId(Form) + file(File，txt/md ≤512KB) | `Response{..., data:{docId,title,charCount}}` |
| GET `/api/v1/kb_list?userId` | Query 参数 | `Response{..., data:[{id,title,charCount,createTime}]}` |
| DELETE `/api/v1/kb_doc?docId&userId` | Query 参数 | `Response{..., data:{deleted}}`（逻辑删除，按归属校验） |

**其他扩展行为：**
- 专家智能体（6 个）经 RunnerNode 注册为可独立对话 agent（agentId=专家名，各自独立会话服务），
  `create_session(agentId="MarketAnalysisAgent")` 即可单独会话；`query_ai_agent_config_list`
  契约不变（仍只返回 investment-advisor）；
- 会话幂等键为 (agentId, userId)：队长与各专家、不同专家之间会话互相独立；
- 本地工具新增 `queryKnowledgeBase`（bean 名 knowledgeBaseMcp，装配时显式并入 ChatModel，
  不改 yml）；`_build_user_context_message` 注入用户知识库文档标题清单（全体智能体可见）；
- 每轮对话（阻塞与流式）落库 MySQL 历史，存储不可用时降级为仅内存会话。

错误码：`E0001` 智能体ID不存在；`0001` 未知失败；`0002` 非法参数。
