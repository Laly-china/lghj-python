# -*- coding: utf-8 -*-
"""
main.py —— 量股化金·预测服务（Prediction Server，端口 8001）

职责：
    对应前端 lghj_web 的 /api/ml/** 代理（vite 代理剥离 /api/ml 前缀后转发到本服务）：
      1. GET /minute/{symbol}   当日 1 分钟分时数据
         —— 返回【裸 JSON 数组】，每项 {"time": "0930", "price": 1800.0,
            "volume": 10000, "avg_price": 1800.0}
         —— 契约来源：
            · Java 主服务 UrlConstant.PREDICTION_API_MINUTE_URL =
              "http://localhost:8001/minute/{symbol}"，且
              RealTimeStockServiceImpl#fetchFromPythonService 用
              JSON.parseObject(response, List.class) 直接把响应体解析为列表；
            · Java 主服务文档（lghj_web/docs/API_Documentation_Detailed.md 2.1.3）
              中分时项字段为 time/price/volume/avg_price，time 为 HHmm 字符串。
      2. GET /predict/{symbol}  LSTM 预测未来 30 天收盘价
         —— 返回【裸 JSON 对象】：
            {"symbol": "sh600519",
             "predictions": [{"date": "2026-10-09", "price": 1810.0}, ... 共 30 项],
             ...附加元信息字段}
         —— 契约来源：前端 request.js 响应拦截器注释明确
            "Prediction service (returns object without code field but with symbol
             and predictions)"，Dashboard.vue 读取 res.data.predictions[i].date/.price。

    symbol 格式：带交易所前缀（sh/sz/bj + 6 位代码，如 sh600519、sz000001、
    bj870357），也兼容裸 6 位代码（自动推断市场）。与 Dashboard.vue 中
    currentSymbol = 'sh000001' 等用法一致。

    与主服务(Result 包装)、Agent 服务(Response 包装)不同，本服务按原系统约定
    返回裸 JSON，无统一包装；错误时返回非 2xx 状态码 + {"error", "msg"} JSON。
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path

# 保证以任意工作目录启动（uvicorn main:app / python main.py）均可 import 同级包
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import data.collector as collector
from model.predictor import PricePredictor, CheckpointNotFoundError, DEFAULT_CHECKPOINT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("prediction-server")

app = FastAPI(
    title="量股化金-预测服务",
    description="分时数据(/minute) 与 LSTM 未来30天股价预测(/predict)，裸 JSON 返回",
    version="1.0.0",
)

# 开发/部署环境均允许跨域（vite 代理场景下不触发，nginx 直连场景下兜底）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 模型单例：进程启动即加载；权重缺失时置为 None，/predict 返回明确错误 JSON
_predictor: PricePredictor | None = None


def get_predictor() -> PricePredictor:
    """惰性获取模型单例（训练脚本重新生成 checkpoint 后无需重启也能生效）。"""
    global _predictor
    if _predictor is None:
        _predictor = PricePredictor()
    return _predictor


@app.get("/")
def root():
    """服务信息。"""
    return {
        "service": "prediction-server",
        "port": 8001,
        "endpoints": ["/minute/{symbol}", "/predict/{symbol}", "/health"],
        "checkpoint": str(DEFAULT_CHECKPOINT.name),
        "checkpoint_loaded": _predictor is not None,
    }


@app.get("/health")
def health():
    """健康检查。"""
    return {"status": "ok", "service": "prediction-server"}


@app.get("/minute/{symbol}")
def minute(symbol: str):
    """
    当日 1 分钟分时数据。

    返回裸 JSON 数组（Java 主服务按 List 解析、前端拦截器对裸数组自动包装）：
        [{"time": "0930", "price": 1800.0, "volume": 10000, "avg_price": 1800.0}, ...]
    """
    try:
        result = collector.get_minute_data(symbol)
    except collector.InvalidSymbolError as e:
        return JSONResponse(status_code=400,
                            content={"error": "invalid_symbol", "msg": str(e)})
    except collector.CollectorError as e:
        logger.error("分时采集失败 symbol=%s: %s", symbol, e)
        return JSONResponse(status_code=502,
                            content={"error": "minute_data_unavailable", "msg": str(e)})
    except Exception as e:  # 兜底，避免 500 堆栈页
        logger.exception("分时接口异常 symbol=%s", symbol)
        return JSONResponse(status_code=500,
                            content={"error": "internal_error", "msg": str(e)})
    return result["items"]


@app.get("/predict/{symbol}")
def predict(symbol: str):
    """
    LSTM 预测未来 30 个交易日收盘价。

    返回裸 JSON 对象（前端拦截器按 symbol+predictions 识别并包装）：
        {
          "symbol": "sh600519",
          "predictions": [{"date": "2026-10-09", "price": 1810.0}, ... 30 项],
          "generated_at": "...",
          "data_date": "2026-09-30",
          "model": {...checkpoint 元信息}
        }
    """
    try:
        sym = collector.parse_symbol(symbol)
    except collector.InvalidSymbolError as e:
        return JSONResponse(status_code=400,
                            content={"error": "invalid_symbol", "msg": str(e)})

    try:
        predictor = get_predictor()
    except CheckpointNotFoundError as e:
        logger.error("模型权重缺失: %s", e)
        return JSONResponse(status_code=503,
                            content={"error": "model_not_ready", "msg": str(e)})
    except Exception as e:
        logger.exception("模型加载失败")
        return JSONResponse(status_code=503,
                            content={"error": "model_load_failed", "msg": str(e)})

    try:
        daily = collector.get_daily_data(sym["symbol"], years=3)
    except collector.InvalidSymbolError as e:
        return JSONResponse(status_code=400,
                            content={"error": "invalid_symbol", "msg": str(e)})
    except collector.CollectorError as e:
        logger.error("日线采集失败 symbol=%s: %s", symbol, e)
        return JSONResponse(status_code=502,
                            content={"error": "data_unavailable", "msg": str(e)})
    except Exception as e:
        logger.exception("日线接口异常 symbol=%s", symbol)
        return JSONResponse(status_code=500,
                            content={"error": "internal_error", "msg": str(e)})

    closes = [item["close"] for item in daily["data"]]
    if len(closes) < predictor.seq_len:
        return JSONResponse(status_code=502, content={
            "error": "insufficient_history",
            "msg": f"历史日线不足: 需要 >= {predictor.seq_len} 个交易日，实际 {len(closes)}"})

    try:
        pred_prices = predictor.predict(closes)
    except Exception as e:
        logger.exception("推理失败 symbol=%s", symbol)
        return JSONResponse(status_code=500,
                            content={"error": "inference_failed", "msg": str(e)})

    # 未来 30 个交易日日期：以日线最后交易日为基准推算
    last_date = daily["data"][-1]["date"]
    try:
        future_dates = collector.next_trade_dates(last_date, len(pred_prices))
    except Exception:
        future_dates = []

    predictions = [{"date": d, "price": round(p, 2)}
                   for d, p in zip(future_dates, pred_prices)]

    return {
        "symbol": sym["symbol"],
        "predictions": predictions,
        "generated_at": collector.now_bj().strftime("%Y-%m-%d %H:%M:%S"),
        "data_date": last_date,
        "model": {
            "type": "LSTM",
            "checkpoint": DEFAULT_CHECKPOINT.name,
            "meta": predictor.meta,
        },
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """所有 HTTPException 统一输出 {"error","msg"} 裸 JSON。"""
    return JSONResponse(status_code=exc.status_code,
                        content={"error": "http_error", "msg": str(exc.detail)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
