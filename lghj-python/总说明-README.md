# 量股化金 Python 复现工程 - 总说明-README

「量股化金」AI 股市量化预测系统，原系统为 Java (Spring Boot) 多服务架构，本工程使用
Python (FastAPI) 忠实复现其 3 个后端服务。所有对外契约（URL、方法、参数名、响应 JSON
字段、状态码、Redis 键名与 TTL）均严格照抄原 Java 实现。

## 一、项目结构

```
lghj-python/                     本工程根目录
├── 总说明-README.md             本文件
├── sql/
│   └── 数据库初始化-init.sql     15 张表建表脚本（原样复制自 feng-lghj/docs/dev-ops/sql/mysql/init.sql）
├── 依赖清单-requirements.txt     venv 基础依赖记录
├── 启动三服务-run-all-services.bat   一键启动 8080/8091/8001（含内部 API token 环境变量）
├── 停止三服务-stop-all-services.bat  一键停止三服务（按端口结束进程）
├── lghj-server/                 主服务（FastAPI，端口 8080，MVC 分层 controller→service→mapper→pojo）
│   ├── 文件清单-file-manifest.md  本服务全部文件的中英文命名对照与职责说明
│   ├── scripts/
│   │   └── 股票导入-import-stocks.py   独立运行的 A 股 Excel 导入脚本
│   └── app/                     Python 源码包（import 机制限制，保留英文命名）
├── ai-agent-server/             AI 智能体服务（端口 8091，DDD 分层，4 个 /api/v1/* 路由）
│   └── 文件清单-file-manifest.md  服务文件清单与接口契约说明
├── prediction-server/           股价预测服务（端口 8001，LSTM 30 日预测）
│   └── 文件清单-file-manifest.md  服务文件清单与接口契约说明
├── streamlit-web/               Streamlit 前端（端口 8501，同花顺风格，替代原 Vue 前端）
│   ├── 文件清单-file-manifest.md  前端文件清单/启动方式/设计说明
│   ├── streamlit_app.py         入口（登录/导航/条件管理端）
│   ├── api.py / components.py   三后端 API 客户端 / 同花顺风格组件与 ECharts 图表
│   ├── .streamlit/config.toml   深色 + THS 红主题（涨红跌绿）
│   ├── app_pages/               7 个页面（行情/个股/交易/自选/AI投顾/社区/管理端）
│   └── 启动前端-run-web.bat      一键启动
├── agent-web/                   AI 投顾终端（NiceGUI，端口 8502，参考 Marvis 布局）
│   ├── 文件清单-file-manifest.md  文件清单/扩展接口依赖说明
│   ├── main.py                  登录 + 马维斯式左栏（新建对话/管家团队/知识库/历史/账户卡片）
│   │                              + 对话主区（实时思考芯片 + 右上角工作指示）
│   ├── api_client.py            8080 登录 / 8091 chat·trace·history·kb 客户端
│   └── 启动投顾终端-run-agent-web.bat  一键启动
└── tests/                       Phase 7 联调自测（pytest 契约测试，73 条用例，
    │                              含 Agent 可视化/历史/知识库扩展接口用例）
    ├── 文件清单-file-manifest.md  测试文件双语说明与运行方式
    ├── API清单-api-inventory.md   前端 7 模块梳理出的全量 API 契约清单（57 项）
    ├── 联调报告-integration-report.md  覆盖率/通过率/bug 清单/端到端结论
    └── conftest.py + test_*.py（7 个）  契约用例（pytest 收集约定保留英文命名）
```

## 二、服务与端口

| 服务 | 端口 | 说明 | 原Java模块 |
| ---- | ---- | ---- | ---------- |
| lghj-server | 8080 | 主服务：登录/账户/股票/行情/K线/新闻/自选股 | feng-lghj/lghj-server |
| ai-agent-server | 8091 | AI 智能体服务（对话/预测解读） | ai-agent-scaffoid-feng |
| prediction-server | 8001 | 股价预测服务（分时/预测，主服务的分时数据来源） | python 预测模块 |

## 三、运行环境（中间件）

- MySQL 8：`127.0.0.1:3306`，库名 `lghj`，账号 `root/123456`
- Redis：`127.0.0.1:6379`，database **8**，无密码
- 两者均由 `env/` 目录内的免安装版提供（**中间件归主控管理，工程代码不要动 env/ 内文件**），
  启动脚本：`env/初始化环境-setup-env.sh`
- Python 虚拟环境：`env/venv-虚拟环境/Scripts/python.exe`（依赖已装齐，直接用该解释器完整路径执行）

## 四、启动方式

### AI 顾问 Key 配置（DEEPSEEK_API_KEY —— 克隆后跑通 AI 投顾的唯一必配项）

AI 能力由 8091 调用 **DeepSeek 的 OpenAI 兼容接口**（模型默认 `deepseek-chat`）实现。
Key 从 **系统环境变量** 读取（项目内无 .env 文件、代码不落盘，因此不会被 git 提交）；
8080/8001 不需要 Key。

1. **获取 Key**：注册 [DeepSeek 开放平台](https://platform.deepseek.com) → 「API Keys」页
   创建，得到 `sk-...` 形式的 Key（账户需有余额或免费额度）。
2. **写入环境变量**（三选一）：
   - Windows 永久（推荐）：`setx DEEPSEEK_API_KEY "sk-你的Key"`（对新开的终端生效），
     或「系统设置 → 高级系统设置 → 环境变量 → 用户变量」新建；
   - Windows 仅当前终端：PowerShell `$env:DEEPSEEK_API_KEY="sk-你的Key"`，
     并在**同一终端**里启动 8091（子进程继承父终端环境）；
   - macOS / Linux：`export DEEPSEEK_API_KEY="sk-你的Key"`（写进 `~/.zshrc` / `~/.bashrc` 持久化）。
   - 兼容回落：也支持原工程变量名 `AI_AGENT_API_KEY`（`DEEPSEEK_API_KEY` 优先）。
3. **重启 8091**：Key 是服务启动时的快照，改完环境变量必须**重启 8091** 才生效
   （已运行的进程不会热加载）。
4. **自检**：登录前端（admin/123456 或注册）向 AI 投顾提问一句即验证；Key 未配置/无效时
   8091 日志出现 `llm completion failed`（DeepSeek 返回 401），前端表现为回答失败。
5. **换模型/供应商**（可选）：`AI_AGENT_MODEL`（如 `deepseek-reasoner`）、
   `AI_AGENT_BASE_URL`（任何 OpenAI 兼容接口），均为环境变量，同样重启生效。

> 内部令牌 `LGHJ_INTERNAL_API_TOKEN`（8091 调 8080 内部接口用）：**双方默认留空 = 不校验**，
> 克隆后不配置也能跑；如需启用，两个服务的该变量保持一致即可。

**一键启动（推荐）**：双击 `启动三服务-run-all-services.bat`（三个命令行窗口分别运行三服务，
含 `LGHJ_INTERNAL_API_TOKEN` 环境变量；停止用 `停止三服务-stop-all-services.bat`）。

**手动启动**（以下相对路径以项目根为基准——`env/` 与 `lghj-python/` 同级；
在服务子目录里执行时解释器相对路径为 `../../env/...`，项目整体挪动位置不影响）：

```bash
# 1. 初始化数据库（MySQL 就绪后执行一次）
mysql -h127.0.0.1 -P3306 -uroot -p123456 < sql/数据库初始化-init.sql

# 2. 启动主服务（uvicorn 入口 app.main:app，端口 8080）
cd lghj-python/lghj-server
"../../env/venv-虚拟环境/Scripts/python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8080

# 3. 启动 AI 智能体服务（端口 8091；需环境变量 DEEPSEEK_API_KEY）
#    LGHJ_INTERNAL_API_TOKEN 与 8080 保持一致（或双方均留空 = 不校验）
cd lghj-python/ai-agent-server
set LGHJ_INTERNAL_API_TOKEN=phase7-internal-token
"../../env/venv-虚拟环境/Scripts/python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8091

# 4. 启动股价预测服务（端口 8001；依赖 model/checkpoints/lstm_30d.pt，无需 MySQL/Redis）
cd lghj-python/prediction-server
"../../env/venv-虚拟环境/Scripts/python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8001

# 5. 导入 A 股基础数据（库内已有 5458 只股票时勿重复导入；也可调用接口 POST /api/admin/stock/import）
cd lghj-python/lghj-server
"../../env/venv-虚拟环境/Scripts/python.exe" scripts/股票导入-import-stocks.py

# 6. 启动 Streamlit 前端（端口 8501，同花顺风格；需三后端已就绪）
cd lghj-python/streamlit-web
"../../env/venv-虚拟环境/Scripts/python.exe" -m streamlit run streamlit_app.py --server.port 8501
#    或直接双击 streamlit-web/启动前端-run-web.bat；浏览器访问 http://127.0.0.1:8501

# 7. 三服务契约自测（8080/8091/8001 全部就绪后执行，可重复运行）
cd lghj-python
"../env/venv-虚拟环境/Scripts/python.exe" -m pytest tests -v
```

## 五、文件命名规则（硬性要求）

- **不被 Python import 的文件**（md/sql/txt/独立脚本）一律 **中文-english 双语命名**，
  例如：`总说明-README.md`、`数据库初始化-init.sql`、`依赖清单-requirements.txt`、
  `股票导入-import-stocks.py`。
- **必须被 import 的源码文件/包目录**（`app`、`main.py`、`controller` 等）因 Python import
  机制限制保留英文名；每个服务目录内的 `文件清单-file-manifest.md` 为每个英文文件标注
  中文职责说明。
- 代码内注释一律中文；每个模块顶部 docstring 标注对应复现的原 Java 类（含相对路径）。

## 六、全局契约

- JWT：HS256，secret=`itfeng`，claims=`{userId, userType}`，请求头名 `token`
  （对应原 Java `application-dev.yml` 的 `lghj.jwt.*`，TTL=7200000000000ms）
- 统一响应体：`Result{code, msg, data}`，成功码 200（对应原 Java `com/lghj/pojo/dto/Result.java`、
  `com/lghj/enums/ErrorEnum.java`）
- JSON 时间格式：`yyyy-MM-dd HH:mm`（对应原 Java `com/lghj/json/JacksonObjectMapper.java`）
- 密码**明文**存储与比对（忠实复现原系统 `LoginServiceImpl` 的行为，生产环境切勿模仿）
- 股票搜索以 MySQL LIKE 替代原 Elasticsearch（symbol 前缀匹配 + name/industry 模糊），
  接口契约不变

## 七、各服务章节

（骨架预留，后续任务在此补充各服务的接口清单与实现说明）

### lghj-server（主服务，Phase 1-4，共 21 个路由模块）

详见 `lghj-server/文件清单-file-manifest.md`。覆盖：登录/JWT、账户、股票搜索（MySQL LIKE
替代 ES）、实时行情/K线/新闻、自选股、模拟交易引擎（混合订单簿撮合）、社区（博客/评论/
关注/Feed）、管理端（用户/博客/评论/股票/交易分页）、内部 API（行情聚合/交易画像，
供 8091 调用，鉴权头 `X-Internal-Token`）。前端 `lghj_web` 的 7 个 api 模块中除
`/api/v1/*`、`/api/ml/*` 外全部路由均由本服务承接，契约逐字照抄原 Java。

### ai-agent-server（AI 智能体服务，Phase 5，端口 8091）

详见 `ai-agent-server/文件清单-file-manifest.md`。DDD 分层复现原 `ai-agent-scaffoid-feng`，
4 个路由挂载在 `/api/v1/*`：`GET query_ai_agent_config_list`、`GET/POST create_session`、
`POST chat`、`POST chat_stream`（文本流）。统一响应体 `Response{code:"0000", info, data}`。
litellm 走 OpenAI 兼容协议调 DeepSeek（环境变量 `DEEPSEEK_API_KEY`）；工具
`querySimTradeProfile` / `queryRealtimeMarket` 经 `X-Internal-Token` 调 8080
`/api/internal/*`。同 (agentId, userId) 的会话幂等复用。另含多个**本工程扩展接口**
（原 Java 无）：`GET /api/v1/trace`（会话执行轨迹：run_start/llm_call/transfer/
tool/agent_text 五种事件）、`GET /api/v1/agent_team`（团队结构）、历史会话
`history_list/history_messages/history_session`（MySQL 持久化）、个人知识库
`kb_upload/kb_list/kb_doc` + 检索工具 `queryKnowledgeBase`；6 个专家智能体注册为
可独立对话 agent。供 AI 投顾终端 agent-web（8502，马维斯式布局：管家团队侧栏 /
实时思考可视化 / 历史会话 / 知识库）与 Streamlit 前端的状态灯可视化使用。

### streamlit-web（Streamlit 前端，8501）

同花顺风格交易终端（原 Vue 前端的替代）：行情/K线/分时/预测/新闻、模拟交易、自选、
社区、管理端，契约与原前端一致。另含**本工程扩展**的马维斯式 AI 投顾体验：侧栏
「管家团队」（队长+6 专家点击单独对话）/「个人知识库」（上传 txt/md，投顾可检索
引用）/「历史对话」（MySQL 持久化、可滑动回看续聊）+ 账户卡片固定左下角；AI 投顾
页发问后实时显示思考过程（右上角"N 位管家工作中"指示 + 管家卡片条状态灯 +
点击下钻思考面板）。依赖 8091 扩展接口，不可用时自动降级。

### prediction-server（股价预测服务，Phase 6，端口 8001）

详见 `prediction-server/文件清单-file-manifest.md`。**裸 JSON 响应**（无包装）：
`GET /minute/{symbol}`（当日分时，akshare 采集 + CSV 缓存，字段 time/price/volume/avg_price）、
`GET /predict/{symbol}`（LSTM 未来 30 个交易日预测，`{symbol, predictions:[{date,price}]×30}`）、
`GET /health`。错误返回裸 JSON `{error, msg}`（400 invalid_symbol / 502 数据不可用 /
503 模型未就绪）。8080 的 `/api/user/realtime/minute` 内部调本服务取分时；模型权重
`model/checkpoints/lstm_30d.pt` 由 `训练模型-train-model.py` 生成（已训好）。

### tests/（Phase 7 三服务联调自测）

详见 `tests/文件清单-file-manifest.md` 与 `tests/联调报告-integration-report.md`：
68 条 pytest 契约用例覆盖 55/55 可测 API（100%），含跨服务链路（8001 分时→8080、
8091 工具→8080 内部 API）与真实 LLM 调用；联调修复 2 个服务缺陷（分时取数超时、
画像接口 Decimal.divide），两轮全量 68/68 通过。后增 Agent 流程可视化扩展接口
用例 3 条（/api/v1/agent_team、/api/v1/trace 结构与工具调用记录），现共 71 条。
