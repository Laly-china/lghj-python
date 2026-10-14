# 项目框架与模块分块 - Architecture & Module Map

「量股化金」AI 股市量化预测系统 · Python (FastAPI) 复现工程
对应原 Java 系统：`lghj-server`(Spring Boot MVC) + `ai-agent-scaffoid-feng`(DDD 多模块) + Python 预测模块

> 本文档为**整体框架梳理**，面向"独立改模块"的维护场景：可据此定位任一功能的归属文件，
> 无需通读全工程。各服务细粒度文件说明见各目录下的 `文件清单-file-manifest.md`。

---

## 一、总体架构

### 1.1 服务拓扑

```
                         ┌──────────────────────────────┐
                         │  streamlit-web  (端口 8501)   │
                         │  同花顺风格前端（替代原 Vue3） │
                         └───────────────┬──────────────┘
                                         │ HTTP（token 头鉴权）
             ┌───────────────────────────┼───────────────────────────┐
             │                           │                           │
             ▼                           ▼                           ▼
  ┌────────────────────┐   ┌────────────────────────┐   ┌─────────────────────┐
  │  lghj-server :8080 │   │ ai-agent-server :8091  │   │ prediction-server   │
  │  主服务（MVC 分层） │   │ AI 投顾（DDD 分层）     │   │ :8001（裸 JSON）     │
  │  登录/账户/股票/行情 │   │ 4 个 /api/v1/* 路由     │   │ LSTM 30 日预测       │
  │  /交易撮合/社区/管理 │   │ litellm→DeepSeek       │   │ akshare 行情采集      │
  └────┬────────┬──────┘   └───────────┬────────────┘   └──────────┬──────────┘
       │        │                      │                            │
       │        │  ① X-Internal-Token  │                            │
       │        └──────────────────────┘  internal API（行情聚合/交易画像）
       │                                                           │
       │  ② httpx 调 8001 /minute（主服务的分时数据来源）             │
       └───────────────────────────────────────────────────────────┘
       │
  ┌────┴──────────────────────────┐
  │  MySQL 8 (127.0.0.1:3306)     │  库 lghj，15 张表
  │  Redis   (127.0.0.1:6379)     │  db=8
  └───────────────────────────────┘
```

### 1.2 三服务职责与响应体契约

| 服务 | 端口 | 分层风格 | 统一响应体 | 依赖中间件 | 对应原 Java |
| --- | --- | --- | --- | --- | --- |
| lghj-server | 8080 | MVC（controller→service→mapper→pojo） | `Result{code,msg,data}`，成功码 **200** | MySQL + Redis | `feng-lghj/lghj-server` |
| ai-agent-server | 8091 | DDD（trigger/api/domain/infrastructure/types） | `Response{code,info,data}`，成功码 **"0000"** | 无（纯调 8080 + DeepSeek） | `ai-agent-scaffoid-feng`（Maven 多模块） |
| prediction-server | 8001 | 平铺（main + data + model） | **裸 JSON**（无包装） | 无（akshare + CSV 缓存） | 原项目 Python 预测模块 |

**三种响应体差异**是前端适配的核心：`streamlit-web/api.py` 按路径前缀分别解析。

### 1.3 跨服务调用链（仅 3 条）

| # | 发起 | 目标 | 用途 | 鉴权 |
| --- | --- | --- | --- | --- |
| ① | 8080 `real_time_stock_service` | 8001 `GET /minute/{symbol}` | 获取当日分时数据（超时 30s） | 无 |
| ② | 8091 `http_ports` | 8080 `GET /api/internal/market/realtime` | Agent 行情工具 | `X-Internal-Token` |
| ③ | 8091 `http_ports` | 8080 `GET /api/internal/sim-trade/profile` | Agent 交易画像工具 | `X-Internal-Token` |

> `LGHJ_INTERNAL_API_TOKEN` 双方一致；**为空时不校验**（原契约语义）。

---

## 二、lghj-server 主服务（8080，8256 行）

### 2.1 分层架构

```
app/main.py ───────────────── 入口：FastAPI 实例 + 路由自动发现 + 拦截器 + 异常处理器
   │
   ├─ app/interceptor.py ────── JWT 中间件（/api/admin/** 与 /api/user/** 两组拦截）
   ├─ app/config.py ─────────── Settings(BaseSettings)，env_prefix="LGHJ_"
   ├─ app/database.py ───────── SQLAlchemy engine / SessionLocal / Base / get_db
   │
   ├─ app/controller/ ───────── 路由层（21 个模块，自动发现，新增文件无需改 main.py）
   │     ├─ notify/            登录/注册/登出
   │     ├─ user/              用户端 9 个模块
   │     ├─ admin/             管理端 6 个模块
   │     └─ internal/          内部 API 2 个模块（供 8091 调用，不走 JWT）
   │
   ├─ app/service/ ──────────── 业务层（17 个模块 + trade 子包 7 个）
   ├─ app/mapper/ ───────────── 数据访问层（16 个模块）
   ├─ app/pojo/ ─────────────── entity(15) / dto(8) / vo(8)
   ├─ app/utils/ ────────────── 工具 7 个（含撮合引擎核心 2 个）
   ├─ app/common/ ───────────── 公共组件 8 个（Result/ErrorEnum/异常/上下文/分页）
   └─ app/task/ ─────────────── 后台任务 3 个（订单恢复 + 3 秒行情调度）
```

### 2.2 模块分块清单

#### A. 入口与基础设施层

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `app/main.py` | 122 | FastAPI 实例；`pkgutil.walk_packages` 递归发现 `controller/` 下所有模块级 `router`；注册 JWT 中间件 + 全局异常；startup 钩子预热 Redis 并调 `task.start()`，shutdown 调 `task.stop()` |
| `app/config.py` | 83 | `Settings(BaseSettings)`，`env_prefix="LGHJ_"`：MySQL(root/123456@127.0.0.1:3306/lghj)、Redis(db=8)、JWT(secret=**itfeng**, TTL=7200000000000ms, 头名 **token**)、外部 URL |
| `app/database.py` | 43 | engine(pool_size=10/max_overflow=10/pool_recycle=3600/pre_ping) + SessionLocal + Base + `get_db()` |
| `app/interceptor.py` | 137 | JWT 校验中间件：`ADMIN_EXCLUDE_PATHS`(3 条) / `USER_EXCLUDE_PATHS`(9 条) 放行清单逐条照抄；`_path_matches()` 等价 Spring AntPathMatcher；401/403 语义照抄 |

#### B. common/ 公共组件

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `common/result.py` | 123 | `Result{code,msg,data}` + **完整 ErrorEnum 码值表**（200/401/500、10001-10003 参数、20001-20012 用户、30001-30010 博客、40001 股票、50001-50005 交易；含原文件重复码值 20006/2007） |
| `common/exception.py` | 73 | `BusinessException` + 全局异常处理器 |
| `common/context.py` | 31 | 当前登录用户上下文（contextvars 替代 ThreadLocal） |
| `common/constants.py` | 62 | Redis 键前缀、外部 URL、状态/密码常量 |
| `common/community_constants.py` | 28 | 社区专用键：`blog:liked:` / `feed:` / `follows:` / `blog:comment:liked:` |
| `common/mp_page.py` | 58 | MyBatis-Plus `Page` JSON 序列化等价实现（`{records,total,size,current,pages,...}`，与 `PageResult{list,total}` **不可混用**） |

#### C. utils/ 工具（含撮合引擎核心）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| **`utils/hybrid_order_book.py`** | **419** | **混合订单簿（冷热分层撮合引擎）**：热=内存优先队列（买价高→低/卖价低→高，容量 100）；冷=Redis ZSet `orderbook:{symbol}:buy/:sell`；现价 ±5% 为热区间；热满溢出降级 50 条；价格变动时冷订单晋升回热。撮合判定：买价≥现价 / 卖价≤现价，按现价全额成交 |
| **`utils/order_queue_manager.py`** | **161** | **每 symbol 单消费者撮合队列**：`asyncio.Queue` + 独立消费者协程（同股串行、跨股并行）；`asyncio.to_thread` 执行同步撮合；`call_soon_threadsafe` 跨线程投递 |
| `utils/lock_util.py` | 99 | Redis 分布式锁：`set(nx=True, px=lease*1000)`；键 `trade:lock:{userId}:{symbol}`，wait=5s/lease=30s |
| `utils/redis_client.py` | 105 | Redis 客户端（db8，`protocol=2` 兼容旧版，socket_timeout=5）；cache_get/set/delete/pattern + JSON 封装；异常一律吞掉降级 |
| `utils/redis_id_worker.py` | 37 | 全局唯一 ID：`时间戳<<32 \| INCR`，键 `icr:{前缀}:{yyyy:MM:dd}` |
| `utils/jwt_util.py` | 36 | JWT HS256 签发/解析，claims=`{userId, userType}` |
| `utils/http_client.py` | 81 | httpx 共享异步客户端，供跨服务调用 8001 |

#### D. service/ 业务层（17 个主模块）

| 文件 | 行数 | 职责 | 对应端点 |
| --- | --- | --- | --- |
| **`service/real_time_stock_service.py`** | **509** | 实时行情(腾讯 `~` 分割,字段 1/2/3/4/5/6/31/32)、历史 K 线(新浪 scale=240/1200/7200 + 腾讯 day/week/month 降级,Redis 24h)、东财新闻 JSONP、分时(调 8001 + 锁防击穿) | `/realtime/*` |
| `service/blog_service.py` | 304 | 博客：发布(feed:ZSet 推送)、点赞(ZSet 成员切换+原子增减)、分页(我的/用户/热度)、详情、Feed 流、删除(清点赞+feed)、编辑、管理端 | `/blog/*` |
| `service/user_manage_service.py` | 301 | 管理端用户：分页查询(`PageResult`)、新增(查重/角色映射/事务)、删除、修改、启停 | `/admin/user` |
| `service/blog_comments_service.py` | 282 | 评论：新增(二级校验)、树形列表、点赞(Set 切换+**非原子**回写)、删除(一级级联)、管理端 | `/blog/comments/*` |
| `service/sim_trade_profile_service.py` | 213 | 交易画像：聚合账户/持仓/订单/成交 → 统计汇总 + **6 个行为标签**(NO_TRADE_RECORD / CONCENTRATED_POSITION / HIGH_ORDER_FREQUENCY / FREQUENT_CANCEL / BUY_SIDE_BIAS / DIVERSIFIED_TRADING) | `/internal/sim-trade/profile` |
| `service/stock_service.py` | 198 | Excel 导入：列解析/代码归一化/市场判定/100 条分批入库 | `/admin/stock/import` |
| `service/user_stock_follow_service.py` | 179 | 自选股增删查：Redis Set `user:stock:follow:{userId}` + DB 双写，列表带行情 | `/optional/*` |
| `service/stock_manage_service.py` | 129 | 管理端股票：keyword 分页、按代码更新、Excel 批量更新 | `/admin/stock/*` |
| `service/login_service.py` | 65 | 登录（账号/**明文密码**/状态校验）与注册 | `/api/login`,`/api/register` |
| `service/account_service.py` | 57 | 模拟账户：创建(初始 20 万)/查询/持仓 | `/user/account/*` |
| `service/follow_service.py` | 53 | 关注/取关（DB + Redis Set `follows:{userId}` 双写） | `/user/follow/*` |
| `service/stock_search_service.py` | 35 | 股票搜索（**MySQL LIKE 替代 ES**，返回 StockDoc） | `/user/stock/search` |
| `service/trade/`（子包） | 参见 E | 交易撮合业务 | `/user/trade/*` |

#### E. service/trade/ 交易撮合子包（7 个模块，共 561 行）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `trade/trade_service.py` | 244 | **交易核心**：`create_order`(冻结→落库→入队) / `_process_trade`(Redis 锁→拉现价→可成交则执行否则挂订单簿) / `cancel_order`(校验归属状态→锁内 status=4→移出订单簿→release) / 订单成交查询。**模块底部完成队列与订单簿处理器装配**（对应 Java `@PostConstruct`） |
| `trade/trade_account_operator.py` | 135 | 账户操作：**乐观锁更新**(`UPDATE ... WHERE version=? AND is_deleted=0`，0 行抛 50004/50003)、持仓逻辑删除、`orderAmount=价格×手数×100` |
| `trade/buy_trade_direction_strategy.py` | 111 | 买入策略：冻结资金(价×手数×100)、撤单解冻、买价≥现价成交、结算=加权平均成本+退差价 |
| `trade/sell_trade_direction_strategy.py` | 89 | 卖出策略：冻结持仓、撤单解冻、卖价≤现价成交、结算=回款+扣减持仓、清仓逻辑删除 |
| `trade/trade_deal_executor.py` | 67 | 成交执行器：成交前校验→插入 trade_deal(`DEAL`+UUID前16)→累计已成交/状态 3 或 2→结算 |
| `trade/trade_direction_strategy.py` | 44 | 方向策略接口：reserve/release/canExecute/validateBeforeDeal/settle |
| `trade/trade_direction_router.py` | 34 | 方向路由：1→买、2→卖 |

#### F. mapper/ 数据访问层（16 个模块，共 1001 行）

`user_mapper`(32) / `user_manage_mapper`(110) / `user_role_mapper`(52) / `blog_mapper`(124) /
`blog_comments_mapper`(141) / `follow_mapper`(62) / `stock_basic_mapper`(69) /
`stock_manage_mapper`(59) / `user_stock_follow_mapper`(43) / `trade_order_mapper`(105) /
`trade_deal_mapper`(60) / `sim_account_mapper`(28) / `user_position_mapper`(33) /
`sim_trade_profile_mapper`(39)。
**关注点**：所有 mapper 均为手写 SQLAlchemy，**不用 ORM 懒加载**，逻辑删除统一 `is_deleted=0` 条件。

#### G. pojo/ 数据对象

- **entity/（15 个，对应 init.sql 15 表）**：`base.py` 提供序列化混入（**JSON 驼峰 + `yyyy-MM-dd HH:mm`**，对应 JacksonObjectMapper）；`sim_account`/`user_position` 含乐观锁 `version`
- **dto/（8 个）**：`login_dto`(16) / `register_dto`(63) / `stock_excel`(23) / `page_result`(20) / `blog_dtos`(49) / `user_manage_dtos`(94)
- **vo/（8 个）**：`login_vo`(19) / `stock_doc`(19) / `stock_news_vo`(19) / `stock_follow_vo`(19) / `blog_vos`(47) / `user_vo`(30)

#### H. controller/ 路由层（21 个模块，共 1115 行）

| 分组 | 模块 | 端点前缀 |
| --- | --- | --- |
| **notify** | `login_controller`(74) | `/api/login` `/api/register` `/api/logout` |
| **user** | `account_controller`(55) | `/api/user/account/*` |
| | `stock_search_controller`(37) | `/api/user/stock/search` `/stock/data` |
| | `real_time_stock_controller`(40) | `/api/user/realtime/quote` `/news` `/minute` |
| | `optional_stock_controller`(47) | `/api/user/optional/*` |
| | `blog`(144) | `/api/user/blog/*` |
| | `comments`(56) | `/api/user/blog/comments/*` |
| | `follow`(34) | `/api/user/follow/*` |
| | `trade`(73) | `/api/user/trade/order` `/cancel` `/query_orders` `/query_deals` |
| **admin** | `user`(77) | `/api/admin/user*` |
| | `blog`(48) | `/api/admin/blog/*` |
| | `comments`(42) | `/api/admin/blog/comments/*` |
| | `stock`(83) | `/api/admin/stock/sync-es` `/init-es` `/page` `/update` `/batch-update` |
| | `stock_controller`(37) | `/api/admin/stock/import`（拦截器放行） |
| | `trade`(74) | `/api/admin/trade/order/page` `/deal/page` |
| **internal** | `market_realtime`(104) | `/api/internal/market/realtime`（`X-Internal-Token`） |
| | `sim_trade_profile`(63) | `/api/internal/sim-trade/profile`（`X-Internal-Token`） |

> **路由自动发现**：在 `controller/` 下任意层级新建文件，只要定义模块级 `router = APIRouter()`，重启即生效，**无需改 main.py 或任何 `__init__.py`**。这是"单独改模块"最友好的设计。

#### I. task/ 后台任务包（3 个模块，共 203 行）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `task/__init__.py` | 70 | 生命周期入口：`start()` 绑定事件循环 → 订单恢复 → 启动 3 秒行情调度；`stop()` 取消调度 + 优雅关闭撮合队列 |
| `task/market_data_scheduler_task.py` | 71 | **每 3 秒**遍历订单簿活跃 symbol 拉行情 → `hybrid_order_book.process_market_data` 触发撮合；单 symbol 失败不影响其他 |
| `task/order_recovery_task.py` | 62 | 启动时查询 status 1/2 未完成订单 → 逐单重新入队，**进程重启后订单簿自动重建** |

#### J. scripts/ 独立脚本（非包）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `scripts/股票导入-import-stocks.py` | 55 | A 股 Excel 独立导入 |
| `scripts/测试脚本-测试订单簿-test-order-book.py` | 94 | 订单簿冷热分层引擎级自测（60 热 + 50 冷精确断言） |

---

## 三、ai-agent-server AI 投顾服务（8091，2413 行）

### 3.1 DDD 分层

```
app/main.py ────────────── FastAPI 入口 + lifespan（应用就绪后执行智能体装配）+ /act/health
app/config.py ──────────── lghj.client 配置 + LLM Key
   │
   ├─ app/types/ ────────── 类型层：constants / response_code(0000/E0001/E0002) / app_exception
   ├─ app/api/ ──────────── 契约层：response.py(Response{code,info,data}) / dto.py(5 个 DTO)
   ├─ app/domain/agent/ ─── 领域层（核心）
   │     ├─ adapter/port.py           出端口接口（MarketDataPort / SimTradeProfilePort）
   │     ├─ adapter/model/            valobj.py(150) + entity.py(67)
   │     └─ service/
   │           ├─ chat_service.py           对话服务（会话复用 + 画像注入）
   │           ├─ armory/armory_service.py  装配服务（遍历配置表驱动装配树）
   │           ├─ armory/factory.py         装配工厂 + DynamicContext + 智能体注册表
   │           ├─ armory/nodes.py(472)      装配树节点链
   │           ├─ armory/runtime.py(367)    ADK 语义轻量运行时
   │           ├─ armory/model_client.py    litellm 客户端
   │           └─ matter/local_tools.py(134) 本地工具（MCP 服务）
   ├─ app/infrastructure/ ─ 基础设施层：http_ports.py(101) httpx 调 8080 内部 API
   ├─ app/trigger/http/ ─── 触发层：agent_controller.py(169) 4 个路由
   └─ app/resources/agent/ ─ 资源：装配 yml ×2 + skills/*.md
```

### 3.2 智能体装配链（核心机制）

```
RootNode → AiApiNode → ChatModelNode → AgentNode → AgentWorkflowNode → RunnerNode
           ↓            ↓               ↓           ↓                     ↓
        baseUrl/     挂载 MCP 工具    构建       路由 loop/parallel/   构建 InMemoryRunner
        apiKey/      +skills 工具     LlmAgent   sequential/supervisor 注册为 bean(bean名=agentId)
        completionsPath
```

- **模板方法模式**：`AbstractArmoryNode.apply()` → `do_apply()` + `get()` 路由下一节点（对齐原 Java `StrategyHandler.apply + router`）
- **6 个专家 Agent**：MarketAnalysis / QuantTechnical / PersonalTradeProfile / RiskAssessment / PortfolioAdvice / ComplianceDisclosure
- **supervisor 编排**：父智能体通过 `transfer_to_agent` 工具把控制权转交直接子智能体（对齐 ADK AutoFlow）；`MAX_TOOL_ROUNDS = 10` 防死循环
- **运行时自研**：原系统用 `google-adk-java` + Spring AI；本工程**手写等价最小运行时**（避免 google-adk-python 与 fastapi/pydantic 版本冲突），`Event.stringify_content()` 对齐 ADK 语义

### 3.3 对外 4 个接口（挂 `/api/v1/*`）

| 方法 路径 | 说明 |
| --- | --- |
| `GET /query_ai_agent_config_list` | 智能体配置列表 |
| `GET`/`POST /create_session` | 创建会话（**同 userId 幂等复用 sessionId**） |
| `POST /chat` | 阻塞对话，返回各事件文本按 `\n` 连接 |
| `POST /chat_stream` | 流式（`text/plain; charset=utf-8` chunked，无 `data:` SSE 前缀） |

### 3.4 chat 上下文注入（`chat_service.py`）

`_build_user_context_message()` 三段拼接，**仅 investment-advisor 注入画像**：
1. 系统提示：限定只能查询当前用户数据
2. 交易画像 JSON（超 6000 字符截断 + `...[truncated]`）
3. 用户问题
> 画像经 `SimTradeProfilePort` → `http_ports` → 8080 `/api/internal/sim-trade/profile` 获取。

---

## 四、prediction-server 预测服务（8001，1139 行）

### 4.1 模块分块

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `main.py` | 215 | FastAPI 入口，3 个端点（`/` `/health` `/minute/{symbol}` `/predict/{symbol}`） |
| `data/collector.py` | 535 | akshare 采集：分时/日线/交易日历 + symbol 解析 + CSV 缓存与失效策略 + 多接口回退 |
| `model/lstm_model.py` | 83 | 网络定义：**2 层 LSTM hidden=64**，输入 60 日归一化收盘 → 输出未来 30 日 |
| `model/predictor.py` | 84 | checkpoint 加载（`weights_only=True`，失败回退）+ 推理（z-score 逐窗口归一化） |
| `训练模型-train-model.py` | 218 | LSTM 训练脚本（独立运行，`--quick` 快速模式） |
| `model/checkpoints/lstm_30d.pt` | - | 训练产物权重 |

### 4.2 数据采集与缓存策略

| 数据 | 主接口 | 回退接口 | 缓存 | 失效规则 |
| --- | --- | --- | --- | --- |
| 股票分时 | `stock_zh_a_hist_min_em(period="1")` | `stock_zh_a_minute`(新浪) | `minute_{symbol}_{YYYYMMDD}.csv` | 覆盖最近应有交易日；同进程 5 分钟去重 |
| 指数分时 | `index_zh_a_hist_min_em` | `stock_zh_a_minute` | 同上 | 同上 |
| 股票日线 | `stock_zh_a_hist(adjust="qfq")` | `stock_zh_a_daily`(新浪) | `daily_{symbol}.csv` | 最新日期 < 最近应有交易日则刷新 |
| 指数日线 | `index_zh_a_hist` | `stock_zh_index_daily`(新浪) | 同上 | 同上 |
| 交易日历 | `tool_trade_date_hist_sina` | 退化按周末规则 | `trade_dates.csv` | mtime 超 30 天刷新 |

### 4.3 接口契约

| 端点 | 返回 |
| --- | --- |
| `GET /minute/{symbol}` | **裸数组** `[{"time":"0930","price":1800.0,"volume":10000,"avg_price":1800.0}]` |
| `GET /predict/{symbol}` | **裸对象** `{"symbol":"sh600519","predictions":[{date,price}×30],...}` |
| 错误 | 非 2xx + `{"error":"<码>","msg":"<中文>"}`：400 `invalid_symbol` / 502 `minute_data_unavailable`·`data_unavailable` / 503 `model_not_ready` |

symbol 格式：`sh/sz/bj` + 6 位（兼容裸 6 位自动推断）；`sh000xxx`/`sz399xxx` 识别为指数。

---

## 五、streamlit-web 前端（8501，2002 行）

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `api.py` | 434 | 三后端客户端：**三种响应体适配** + token 注入 + 401 强制登出 + 全量接口封装（带 `st.cache_data` 短缓存） |
| `components.py` | 281 | 同花顺风格：涨红跌绿 Styler、行情头部、三大指数看板、ECharts option 构造 |
| `streamlit_app.py` | 89 | 入口：`st.navigation` 分组导航（未登录=独立登录屏；管理端仅 userType=3） |
| `app_pages/管理端-admin.py` | 295 | 用户/股票/博客/评论/委托/成交 |
| `app_pages/交易-trade.py` | 234 | 开户、账户指标、买卖委托、撤单、持仓、记录 |
| `app_pages/社区-community.py` | 190 | 四标签流、发布、点赞、关注、二级评论树 |
| `app_pages/行情-market.py` | 117 | 三大指数（5 秒自刷新）、搜索、自选速览 |
| `app_pages/个股-stock.py` | 110 | 行情头部 + 分时/K线/预测/新闻 四懒加载标签 |
| `app_pages/登录-login.py` | 102 | 独立登录/注册屏 |
| `app_pages/AI投顾-advisor.py` | 82 | 智能体选择、会话复用、chat |
| `app_pages/自选-watchlist.py` | 68 | 自选股列表（着色 + 跳转/移除） |

---

## 六、tests/ 契约自测（1544 行，68 条用例）

| 文件 | 行数 | 覆盖模块 | 用例数 |
| --- | --- | --- | --- |
| `conftest.py` | 203 | 公共夹具（随机用户 + 自清理） | - |
| `test_trade.py` | 283 | 建户/账户/持仓/下单/撤单/委托/成交 | 12 |
| `test_community.py` | 243 | 博客 CRUD/点赞/评论树/Feed | 9 |
| `test_admin.py` | 234 | 用户/博客/评论/股票/交易分页 | 11 |
| `test_agent.py` | 215 | 8091 四接口（真调 LLM） | 10 |
| `test_auth.py` | 144 | 登录/注册/登出 | 13 |
| `test_stock.py` | 131 | 搜索/K线/自选/行情 | 7 |
| `test_ml.py` | 91 | 8001 分时/预测 + 8080 跨服务链路 | 6 |

---

## 七、核心机制速查

### 7.1 交易撮合全链路

```
① POST /api/user/trade/order
   └─ trade_service.create_order
       ├─ order_no = "ORDER" + uuid4().hex[:16]，status=1
       ├─ strategy.reserve() 冻结资金/持仓
       ├─ 落库 commit
       └─ order_queue_manager.add_order()  ── 入 per-symbol asyncio.Queue

② 消费者协程 _consume_loop（每 symbol 一个）
   └─ await asyncio.to_thread(trade_service.process_order)
       ├─ Redis 锁 trade:lock:{userId}:{symbol}（wait=5s/lease=30s）
       ├─ 拉现价（asyncio.run_coroutine_threadsafe 调行情，超时 15s，兜底 10.00）
       ├─ strategy.can_execute(price)
       ├─ 可成交 → trade_deal_executor.execute（插 trade_deal，status=3 或 2）
       └─ 不可成交 → hybrid_order_book.add_limit_order（挂订单簿）

③ 每 3 秒 MarketDataSchedulerTask.update_market_data
   └─ 遍历活跃 symbol → 拉行情 → hybrid_order_book.process_market_data
       └─ 触发挂单撮合（热队列优先，冷队列按 ±5% 区间晋升）

④ 进程重启 → OrderRecoveryTask.recover_unfinished_orders
   └─ 查询 status 1/2 → 重新入队 → 重建订单簿
```

**装配点（模块导入即完成，对应 Java `@PostConstruct`）**：
```python
# trade_service.py 模块底部
order_queue_manager.set_order_processor(trade_service.process_order)
hybrid_order_book.set_order_processor(order_queue_manager.add_order)
```

### 7.2 JWT 鉴权与放行清单

| 拦截组 | 路径规则 | 校验内容 | 放行清单 |
| --- | --- | --- | --- |
| ADMIN | `/api/admin/**` | userType 必须 = 3 | `/api/login`、`/api/admin/stock/import`、`/api/admin/stock/init-es` |
| USER | `/api/user/**` | 仅校验 userId 存在 | 9 条：blog/comments/list、realtime/quote、realtime/news、realtime/minute、blog/query/hot、blog/query/of/user、stock/search、stock/data |
| 不拦截 | `/api/internal/**` | 控制器自行校验 `X-Internal-Token` | — |

### 7.3 统一响应体三态

| 服务 | 结构 | 成功码 | 错误码示例 |
| --- | --- | --- | --- |
| 8080 | `{code:int, msg:str, data:any}` | `200` | `500` 系统异常、`401` 未登录、`50001` 资金不足、`50002` 持仓不足 |
| 8091 | `{code:"0000", info:str, data:any}` | `"0000"` | `"0001"` 未知失败、`"E0001"` 智能体不存在 |
| 8001 | 裸 JSON | — | `{"error":"invalid_symbol","msg":"..."}` |

### 7.4 Redis 键位表

| 键 | 类型 | 用途 | 写入方 |
| --- | --- | --- | --- |
| `orderbook:{symbol}:buy` / `:sell` | ZSet | 冷订单簿（member=订单JSON，score=价格） | hybrid_order_book |
| `trade:lock:{userId}:{symbol}` | String(NX PX) | 撮合分布式锁 wait5s/lease30s | lock_util |
| `user:stock:follow:{userId}` | Set | 自选股 | user_stock_follow_service |
| `blog:liked:{blogId}` | ZSet | 博客点赞 | blog_service |
| `blog:comment:liked:{commentId}` | Set | 评论点赞 | blog_comments_service |
| `feed:{userId}` | ZSet | Feed 收件箱（score=毫秒时间戳） | blog_service |
| `follows:{userId}` | Set | 关注集合 | follow_service |
| `icr:{前缀}:{yyyy:MM:dd}` | String(INCR) | 全局唯一 ID | redis_id_worker |

---

## 八、模块改动指南（"单独改模块"速查）

| 想改什么 | 改哪里 | 是否需动其他文件 |
| --- | --- | --- |
| 新增一个用户端接口 | `lghj-server/app/controller/user/xxx.py` 新建 + 定义 `router` | **否**（自动发现） |
| 新增业务逻辑 | `lghj-server/app/service/xxx_service.py` | 否 |
| 新增表字段 | `sql/数据库初始化-init.sql` + `app/pojo/entity/xxx.py` + `app/mapper/xxx_mapper.py` | 是（三处同步） |
| 改响应体/错误码 | `lghj-server/app/common/result.py` | 否 |
| 改撮合算法 | `lghj-server/app/utils/hybrid_order_book.py` | 否 |
| 改撮合流程/锁 | `lghj-server/app/service/trade/trade_service.py` | 否 |
| 改调度频率 | `lghj-server/app/task/market_data_scheduler_task.py`（`SCHEDULE_INTERVAL_SECONDS`） | 否 |
| 改买/卖规则 | `lghj-server/app/service/trade/buy_/sell_trade_direction_strategy.py` | 否 |
| 改放行清单/鉴权 | `lghj-server/app/interceptor.py` | 否 |
| 改端口/密码/密钥 | 环境变量 `LGHJ_*` 覆盖（**无需改代码**） | 否 |
| 新增 Agent 工具 | `ai-agent-server/app/domain/agent/service/matter/local_tools.py` + `resources/agent/*.yml` 挂载 | 是（工具 + 装配 yml） |
| 改 Agent 装配链 | `ai-agent-server/app/domain/agent/service/armory/nodes.py` | 否 |
| 改预测模型 | `prediction-server/model/lstm_model.py` + 重跑 `训练模型-train-model.py` | 是（重训权重） |
| 改采购数据源 | `prediction-server/data/collector.py` | 否 |
| 改前端页面 | `streamlit-web/app_pages/*.py` | 否 |
| 新增前端接口调用 | `streamlit-web/api.py` | 否 |

---

## 九、工程约定（硬性）

1. **命名规则**：不被 import 的文件用 `中文-english` 双语命名；必须被 import 的源码保留英文名
2. **注释语言**：代码内注释一律中文；每个模块顶部 docstring 标注对应复现的原 Java 类（相对路径）
3. **契约优先**：URL、方法、参数名、响应 JSON 字段、状态码、Redis 键名与 TTL **逐字照抄**原 Java
4. **忠实复现**：原系统缺陷（明文密码、非原子点赞、NPE 热点博客、`divide` 语义等）**保留不修**
5. **配置外部化**：全部配置可用 `LGHJ_` 前缀环境变量覆盖，实现"项目零改动"适配不同环境
6. **中间件归主控**：`env/` 目录内文件不要动

---

## 十、规模总览

| 单元 | py 文件数 | 代码行数 | 说明 |
| --- | --- | --- | --- |
| lghj-server | 111 | 8,256 | 主服务（最大） |
| ai-agent-server | 34 | 2,413 | AI 投顾 |
| streamlit-web | 11 | 2,002 | 前端 |
| prediction-server | 7 | 1,139 | 预测服务 |
| tests | 8 | 1,544 | 契约自测 |
| **合计** | **175** | **15,354** | 另有 11 份中文 md 文档 |

**依赖清单**：`依赖清单-requirements.txt`（根）+ `ai-agent-server/依赖清单-requirements-ai-agent.txt` + `prediction-server/依赖清单-requirements-prediction.txt`

**启动脚本**：`启动三服务-run-all-services.bat` / `停止三服务-stop-all-services.bat` / `streamlit-web/启动前端-run-web.bat`
