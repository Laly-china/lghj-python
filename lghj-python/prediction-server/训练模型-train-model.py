# -*- coding: utf-8 -*-
"""
训练模型-train-model.py —— LSTM 未来 30 天收盘价模型训练脚本（独立运行，不被 import）

用法（使用项目 venv 解释器，在 prediction-server 目录下执行；项目根 = env/ 与 lghj-python/ 的上一级）：
    "..\\..\\env\\venv-虚拟环境\\Scripts\\python.exe" 训练模型-train-model.py
可选参数：
    --symbols sh600519,sz000001,...  训练用股票（默认 10 只主流 A 股，带交易所前缀）
    --epochs 30                      最大训练轮数（默认 30，配合早停）
    --quick                          快速冒烟模式（2 只股票、5 轮，几分钟内出 checkpoint）
    --seq-len 60 --pred-len 30 --hidden 64 --layers 2 --batch 32 --lr 0.001
    --out model/checkpoints/lstm_30d.pt

流程：
    1. 通过 data/collector.py 采集各股近 3 年日线（前复权，自动读写 data/cache/）；
       网络不可用时降级用本地缓存；全部不可用时用几何布朗运动合成数据兜底，
       保证总能产出一个结构可用 checkpoint（meta.data_source 会标注 synthetic）。
    2. 构造滑窗样本：输入最近 60 日收盘（逐窗口 z-score 归一化），
       目标为紧随其后的 30 日收盘（用同一窗口均值/标准差归一化）。
    3. 训练 model/lstm_model.py 的 LSTMForecast（MSE + Adam，CPU 单机），
       按时间顺序 9:1 划分训练/验证窗口，验证损失早停。
    4. 保存 {"model_state","config","meta"} 到 model/checkpoints/lstm_30d.pt，
       与 model/predictor.py 的加载格式一致。
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import torch
import torch.nn as nn

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from data import collector                      # noqa: E402
from model.lstm_model import (                  # noqa: E402
    LSTMForecast, normalize_window, denormalize,
    DEFAULT_SEQ_LEN, DEFAULT_PRED_LEN, DEFAULT_HIDDEN, DEFAULT_LAYERS, DEFAULT_DROPOUT,
)

DEFAULT_SYMBOLS = ("sh600519,sz000001,sh600036,sz000858,sh601318,"
                   "sz300750,sh600276,sz000333,sh601899,sh688981")
CHECKPOINT_DIR = BASE_DIR / "model" / "checkpoints"


def log(msg: str) -> None:
    """带时间戳的进度输出（避免长时间无输出被误判假死）。"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def collect_training_series(symbols: list, seq_len: int, pred_len: int) -> tuple:
    """
    采集训练用收盘价序列。返回 (series_list, data_source, used_symbols)。
    series_list: 每个元素是一只股票的收盘价 float 列表（升序按交易日）。
    """
    series, used = [], []
    for s in symbols:
        try:
            daily = collector.get_daily_data(s, years=3)
            closes = [item["close"] for item in daily["data"] if item["close"]]
            if len(closes) >= seq_len + pred_len + 50:
                series.append(closes)
                used.append(s)
                log(f"  采集成功 {s}: {len(closes)} 个交易日 "
                    f"({daily['data'][0]['date']} ~ {daily['data'][-1]['date']})")
            else:
                log(f"  跳过 {s}: 日线不足({len(closes)})")
        except Exception as e:
            log(f"  跳过 {s}: 采集失败 {e}")
    if series:
        return series, "akshare/缓存", used
    # 兜底：几何布朗运动合成数据，保证能产出结构可用的 checkpoint
    log("  全部股票采集失败，改用几何布朗运动(GBM)合成数据训练（仅保证接口可用）")
    for k in range(3):
        random.seed(42 + k)
        closes, price = [], 100.0 * (1 + k * 0.5)
        for _ in range(900):
            price *= (1 + random.gauss(0.0003, 0.02))
            closes.append(price)
        series.append(closes)
    return series, "synthetic(GBM)", [f"synthetic_{i}" for i in range(len(series))]


def build_windows(series: list, seq_len: int, pred_len: int) -> tuple:
    """滑窗构造样本：逐窗口 z-score 归一化输入与目标。返回 (X, Y) 张量。"""
    xs, ys = [], []
    for closes in series:
        for i in range(0, len(closes) - seq_len - pred_len + 1):
            window = closes[i: i + seq_len]
            target = closes[i + seq_len: i + seq_len + pred_len]
            norm, mean, std = normalize_window([float(v) for v in window])
            xs.append(norm)
            ys.append([(v - mean) / std for v in target])
    x = torch.tensor(xs, dtype=torch.float32).unsqueeze(-1)   # (N, seq_len, 1)
    y = torch.tensor(ys, dtype=torch.float32)                 # (N, pred_len)
    return x, y


def main() -> None:
    parser = argparse.ArgumentParser(description="LSTM 未来30天收盘价训练脚本")
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS, help="逗号分隔的股票代码")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--seq-len", type=int, default=DEFAULT_SEQ_LEN)
    parser.add_argument("--pred-len", type=int, default=DEFAULT_PRED_LEN)
    parser.add_argument("--hidden", type=int, default=DEFAULT_HIDDEN)
    parser.add_argument("--layers", type=int, default=DEFAULT_LAYERS)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--out", default="model/checkpoints/lstm_30d.pt")
    parser.add_argument("--quick", action="store_true", help="快速冒烟模式")
    args = parser.parse_args()

    if args.quick:
        args.symbols = "sh600519,sz000001"
        args.epochs = 5
    symbols = [s.strip().lower() for s in args.symbols.split(",") if s.strip()]

    torch.manual_seed(42)
    t0 = time.time()
    log(f"训练配置: symbols={symbols} epochs={args.epochs} seq={args.seq_len} "
        f"pred={args.pred_len} hidden={args.hidden} layers={args.layers}")

    # 1. 采集数据
    log("步骤1/4 采集日线数据...")
    series, data_source, used = collect_training_series(symbols, args.seq_len, args.pred_len)

    # 2. 构造窗口样本（按时间 9:1 划分训练/验证）
    log("步骤2/4 构造滑窗样本...")
    train_series = [s[: int(len(s) * 0.92)] for s in series]
    val_series = [s[int(len(s) * 0.92) - args.seq_len:] for s in series]
    x_train, y_train = build_windows(train_series, args.seq_len, args.pred_len)
    x_val, y_val = build_windows(val_series, args.seq_len, args.pred_len)
    if len(x_train) == 0:
        log("训练样本为空，终止")
        sys.exit(1)
    log(f"样本量: 训练 {len(x_train)} / 验证 {max(len(x_val), 0)} 窗口")

    # 3. 训练
    log("步骤3/4 训练 LSTM (CPU)...")
    model = LSTMForecast(hidden_size=args.hidden, num_layers=args.layers,
                         pred_len=args.pred_len, dropout=DEFAULT_DROPOUT)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=3)
    loss_fn = nn.MSELoss()
    n_params = sum(p.numel() for p in model.parameters())
    log(f"模型参数量: {n_params}")

    patience, best_val, best_state, bad_epochs = 6, float("inf"), None, 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        perm = torch.randperm(len(x_train))
        total = 0.0
        for i in range(0, len(perm), args.batch):
            idx = perm[i: i + args.batch]
            opt.zero_grad()
            loss = loss_fn(model(x_train[idx]), y_train[idx])
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            total += loss.item() * len(idx)
        train_loss = total / len(x_train)

        model.eval()
        with torch.no_grad():
            val_loss = loss_fn(model(x_val), y_val).item() if len(x_val) > 0 else train_loss
        sched.step(val_loss)
        log(f"epoch {epoch:03d}/{args.epochs}  train_mse={train_loss:.6f} "
            f"val_mse={val_loss:.6f}  elapsed={time.time() - t0:.0f}s")
        if val_loss < best_val - 1e-6:
            best_val, best_state, bad_epochs = val_loss, model.state_dict(), 0
        else:
            bad_epochs += 1
            if bad_epochs >= patience:
                log(f"验证损失连续 {patience} 轮未改善，早停")
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    # 4. 保存 checkpoint（与 model/predictor.py 加载格式一致）
    out_path = BASE_DIR / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "model_state": model.state_dict(),
        "config": {"hidden_size": args.hidden, "num_layers": args.layers,
                   "pred_len": args.pred_len, "dropout": DEFAULT_DROPOUT},
        "meta": {
            "seq_len": args.seq_len,
            "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbols": used,
            "n_train_windows": int(len(x_train)),
            "val_mse_norm": round(best_val, 6),
            "epochs_ran": epoch,
            "data_source": data_source,
        },
    }
    torch.save(checkpoint, out_path)
    log(f"步骤4/4 checkpoint 已保存: {out_path}")
    log(f"完成，总耗时 {time.time() - t0:.0f}s，最优验证 MSE(归一化)={best_val:.6f}")

    # 自检：用训练集最后一段做一次演示推理
    demo = series[0][-args.seq_len:]
    norm, mean, std = normalize_window(demo)
    with torch.no_grad():
        pred = model(torch.tensor(norm, dtype=torch.float32).view(1, -1, 1))[0].tolist()
    demo_pred = denormalize(pred, mean, std)
    log(f"演示推理({used[0]} 最后{args.seq_len}日→未来{args.pred_len}日): "
        f"首日={demo_pred[0]:.2f} 末日={demo_pred[-1]:.2f}")


if __name__ == "__main__":
    main()
