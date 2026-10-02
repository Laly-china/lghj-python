# 文件清单 - File Manifest（量股化金 · 预测服务 prediction-server，端口 8001）

本服务为「量股化金」股票模拟交易平台 Python 复现工程的 **Phase 6：预测服务**。
原 Java 仓库无该服务源码，接口契约依据前端 `lghj_web` 源码与 Java 主服务源码中的调用约定全新编写。

## 服务概述

| 项目 | 说明 |
| :--- | :--- |
| 端口 | 8001 |
| 框架 | FastAPI + uvicorn |
| 启动方式 | 在本目录执行 `"..\..\env\venv-虚拟环境\Scripts\python.exe" main.py`，或 `..\..\env\venv-虚拟环境\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8001`（项目根 = env/ 与 lghj-python/ 的上一级） |
| 响应格式 | **裸 JSON，无统一包装**（区别于主服务 Result 包装、Agent 服务 Response 包装） |
| 数据依赖 | 仅 akshare 外网行情 + 本地 CSV 缓存，**不需要 MySQL/Redis** |

## 接口契约（依据前端/主服务源码调研）

前端 `lghj_web/src/api/stock.js`：
- `getRealtimeMinute(symbol)` → `GET /ml/minute/{symbol}`，vite 代理剥离 `/api/ml` 后即本服务 `GET /minute/{symbol}`
- `getPrediction(symbol)` → `GET /ml/predict/{symbol}` → 本服务 `GET /predict/{symbol}`

`GET /minute/{symbol}` 返回**裸 JSON 数组**（Java 主服务 `RealTimeStockServiceImpl#fetchFromPythonService`
以 `JSON.parseObject(response, List.class)` 整体解析；字段见 Java 主服务文档 2.1.3）：

```json
[{"time": "0930", "price": 1800.0, "volume": 10000, "avg_price": 1800.0}]
```

`GET /predict/{symbol}` 返回**裸 JSON 对象**（前端 `request.js` 拦截器注释明确
"returns object without code field but with symbol and predictions"；
`Dashboard.vue` 读取 `res.data.predictions[i].date / .price`）：

```json
{
    "symbol": "sh600519",
    "predictions": [{"date": "2026-10-09", "price": 1810.0}]
}
```

`predictions` 固定 30 项（未来 30 个交易日，日期按交易日历推算）。

symbol 格式：`sh/sz/bj + 6 位代码`（如 sh600519、sz000001、bj870357），兼容裸 6 位代码
（自动推断市场）；`sh000xxx`/`sz399xxx` 识别为指数（如 Dashboard 默认的 sh000001 上证指数）。

## 文件清单

```
prediction-server/
├── 文件清单-file-manifest.md                  # 本文件（双语说明）
├── 依赖清单-requirements-prediction.txt       # Python 依赖清单（独立文档，不被 import）
├── 训练模型-train-model.py                    # LSTM 训练脚本（独立运行，不被 import）
│                                              #   用法: "...python.exe" 训练模型-train-model.py [--quick]
├── main.py                                    # FastAPI 入口（端口 8001，/minute /predict /health）
├── data/                                      # 行情采集模块 + 缓存（代码按路径引用，保留英文名）
│   ├── __init__.py                            # 包声明
│   ├── collector.py                           # akshare 采集：分时/日线/交易日历，symbol 解析，
│   │                                          #   CSV 缓存与日期失效策略、失败降级
│   └── cache/                                 # 采集数据本地缓存（自动生成，可整目录删除重建）
│       ├── minute_{symbol}_{YYYYMMDD}.csv     #   分时缓存（按数据日期命名，当日复用）
│       ├── daily_{symbol}.csv                 #   日线缓存（近 3 年，按最新日期判定失效）
│       └── trade_dates.csv                    #   交易日历缓存（30 天有效期）
└── model/                                     # LSTM 模型（代码按路径引用，保留英文名）
    ├── __init__.py                            # 包声明
    ├── lstm_model.py                          # 网络定义：2 层 LSTM hidden=64，
    │                                          #   输入 60 日归一化收盘 → 输出未来 30 日
    ├── predictor.py                           # checkpoint 加载 + 推理（/predict 使用）
    └── checkpoints/                           # 权重目录
        └── lstm_30d.pt                        # 训练产物（由 训练模型-train-model.py 生成）
```

## 命名说明（用户硬性要求）

- **不被 Python import 的文件**用中文-english 双语命名：
  `文件清单-file-manifest.md`、`依赖清单-requirements-prediction.txt`、`训练模型-train-model.py`
- **代码中按路径引用的目录**保留英文：`data/`（含 `cache/`）、`model/`（含 `checkpoints/`）
- **必须被 import 的源码文件**保留英文名：`main.py`、`data/__init__.py`、`data/collector.py`、
  `model/__init__.py`、`model/lstm_model.py`、`model/predictor.py`

## 缓存失效策略（data/cache/）

| 缓存 | 命名/判定 | 失效规则 |
| :--- | :--- | :--- |
| 分时 | `minute_{symbol}_{YYYYMMDD}.csv`（YYYYMMDD=数据日期） | 缓存数据日期已覆盖"最近应有交易日"则复用；同进程 5 分钟内同数据日期不重复请求；网络失败降级读最近缓存 |
| 日线 | `daily_{symbol}.csv` | 缓存最新日期 < 最近应有交易日则在线刷新，失败降级旧缓存 |
| 交易日历 | `trade_dates.csv` | 文件 mtime 超 30 天则刷新；失败退化为"跳过周末"推算 |

## akshare 接口选型（主接口 → 回退接口，均经实测）

| 数据 | 主接口 | 回退接口（实测可用） |
| :--- | :--- | :--- |
| 股票分时 | `stock_zh_a_hist_min_em(period="1")` | `stock_zh_a_minute`（新浪，带前缀 symbol） |
| 指数分时 | `index_zh_a_hist_min_em(period="1")` | `stock_zh_a_minute`（新浪，sh000xxx/sz399xxx 亦可） |
| 股票日线 | `stock_zh_a_hist(adjust="qfq")` | `stock_zh_a_daily`（新浪，前复权） |
| 指数日线 | `index_zh_a_hist` | `stock_zh_index_daily`（新浪；实测东财指数接口在本网络环境被拒，新浪可用） |
| 交易日历 | `tool_trade_date_hist_sina` | 退化：按周末规则推算 |

## 错误返回约定

非 2xx 状态码 + `{"error": "<错误码>", "msg": "<中文说明>"}` 裸 JSON：
- 400 `invalid_symbol`：symbol 格式非法
- 502 `minute_data_unavailable` / `data_unavailable`：外网采集失败且无可用缓存
- 503 `model_not_ready`：`model/checkpoints/lstm_30d.pt` 缺失（需先跑训练脚本）
- 500 `internal_error` / `inference_failed`：服务内部异常
