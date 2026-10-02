# -*- coding: utf-8 -*-
"""
model/predictor.py —— checkpoint 加载与未来 30 天收盘价推理

职责：
    1. 从 model/checkpoints/ 下的 .pt 文件加载 LSTM 权重与配置；
       文件不存在时抛出 CheckpointNotFoundError（由 main.py 转成明确的错误 JSON）。
    2. 输入最近 >= 60 个交易日的收盘价序列，取最后 60 日做逐窗口 z-score 归一化，
       前向推理得到未来 30 个交易日的收盘价（反归一化后返回原生 float 列表）。

checkpoint 格式（由 训练模型-train-model.py 生成）：
    {
        "model_state": state_dict,
        "config": {"hidden_size": 64, "num_layers": 2, "pred_len": 30, "dropout": 0.1},
        "meta": {"seq_len": 60, "trained_at": "...", "symbols": [...], "val_loss": ...}
    }
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import torch

from model.lstm_model import (LSTMForecast, normalize_window, denormalize,
                              DEFAULT_SEQ_LEN, DEFAULT_PRED_LEN)

logger = logging.getLogger("prediction-server.predictor")

BASE_DIR = Path(__file__).resolve().parent.parent          # prediction-server/
CHECKPOINT_DIR = BASE_DIR / "model" / "checkpoints"        # 权重目录（代码按路径引用，保留英文）
DEFAULT_CHECKPOINT = CHECKPOINT_DIR / "lstm_30d.pt"


class CheckpointNotFoundError(FileNotFoundError):
    """模型权重文件缺失。"""


class PricePredictor:
    """加载一次 checkpoint，可反复调用 predict()。"""

    def __init__(self, checkpoint_path: Optional[Path] = None):
        self.path = Path(checkpoint_path) if checkpoint_path else DEFAULT_CHECKPOINT
        if not self.path.exists():
            raise CheckpointNotFoundError(
                f"模型权重文件不存在: {self.path}，请先运行 训练模型-train-model.py 生成")
        # torch>=2.6 默认 weights_only=True；checkpoint 内仅含张量与基本类型，可直接安全加载
        try:
            ckpt = torch.load(self.path, map_location="cpu", weights_only=True)
        except Exception:
            ckpt = torch.load(self.path, map_location="cpu", weights_only=False)

        cfg = ckpt.get("config", {})
        self.seq_len = int(ckpt.get("meta", {}).get("seq_len", DEFAULT_SEQ_LEN))
        self.model = LSTMForecast(
            hidden_size=int(cfg.get("hidden_size", 64)),
            num_layers=int(cfg.get("num_layers", 2)),
            pred_len=int(cfg.get("pred_len", DEFAULT_PRED_LEN)),
            dropout=float(cfg.get("dropout", 0.1)),
        )
        self.model.load_state_dict(ckpt["model_state"])
        self.model.eval()
        self.meta: dict = ckpt.get("meta", {})
        logger.info("已加载模型权重 %s (meta=%s)", self.path.name, self.meta)

    @property
    def pred_len(self) -> int:
        return self.model.pred_len

    def predict(self, closes: list) -> list:
        """
        输入历史收盘价列表（升序按交易日，长度 >= seq_len），
        返回未来 pred_len 个交易日的收盘价（float 列表，原生类型）。
        """
        if closes is None or len(closes) < self.seq_len:
            raise ValueError(
                f"历史收盘价不足: 需要 >= {self.seq_len} 个交易日，实际 {0 if not closes else len(closes)}")
        window = [float(v) for v in closes[-self.seq_len:]]
        norm, mean, std = normalize_window(window)
        x = torch.tensor(norm, dtype=torch.float32).view(1, -1, 1)
        with torch.no_grad():
            y = self.model(x)[0].tolist()
        return [round(v, 4) for v in denormalize(y, mean, std)]
