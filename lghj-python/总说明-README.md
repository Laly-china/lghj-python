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
└── tests/                       Phase 7 联调自测（pytest 契约测试，68 条用例）
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
`/api/internal/*`。同 userId 的会话幂等复用。

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
画像接口 Decimal.divide），两轮全量 68/68 通过。
