# -*- coding: utf-8 -*-
"""
model/lstm_model.py —— LSTM 网络结构定义

职责：
    定义"收盘价序列 → 未来 30 天收盘价"的 LSTM 预测网络。
    输入：最近 seq_len（默认 60）个交易日的归一化收盘价序列，形状 (B, seq_len, 1)；
    输出：未来 pred_len（默认 30）个交易日的归一化收盘价，形状 (B, pred_len)。

规模控制：
    2 层 LSTM、hidden=64，参数量约 5 万，CPU 上数分钟内可完成训练（见
    训练模型-train-model.py）。

归一化约定（与 predictor / 训练脚本保持一致）：
    对每个输入窗口做逐窗口 z-score 标准化（减窗口均值、除窗口标准差），
    训练目标（未来 30 天收盘价）用同一窗口的均值/标准差归一化。
    因此模型本身对价格量纲不敏感，推理时无需保存全局 scaler。
"""
from __future__ import annotations

import torch
import torch.nn as nn

# 默认超参数（训练脚本与推理加载共用）
DEFAULT_SEQ_LEN = 60    # 输入窗口长度（交易日）
DEFAULT_PRED_LEN = 30   # 预测未来交易日数
DEFAULT_HIDDEN = 64     # LSTM 隐层维度
DEFAULT_LAYERS = 2      # LSTM 层数
DEFAULT_DROPOUT = 0.1


class LSTMForecast(nn.Module):
    """输入最近 seq_len 日归一化收盘价，输出未来 pred_len 日归一化收盘价。"""

    def __init__(self, hidden_size: int = DEFAULT_HIDDEN,
                 num_layers: int = DEFAULT_LAYERS,
                 pred_len: int = DEFAULT_PRED_LEN,
                 dropout: float = DEFAULT_DROPOUT):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.pred_len = pred_len
        self.lstm = nn.LSTM(
            input_size=1,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, pred_len),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: (B, seq_len, 1) 归一化收盘价序列
        返回: (B, pred_len) 归一化预测值
        """
        out, _ = self.lstm(x)          # (B, seq_len, hidden)
        last = out[:, -1, :]           # 取最后时间步 (B, hidden)
        return self.head(last)         # (B, pred_len)


def normalize_window(window: list) -> tuple:
    """
    逐窗口 z-score 标准化。
    返回 (归一化序列, mean, std)；标准差过小时退化为 1，避免除零。
    """
    n = len(window)
    mean = sum(window) / n
    var = sum((v - mean) ** 2 for v in window) / max(n - 1, 1)
    std = var ** 0.5
    if std < 1e-8:
        std = 1e-8
    norm = [(v - mean) / std for v in window]
    return norm, mean, std


def denormalize(values: list, mean: float, std: float) -> list:
    """反归一化：还原为真实价格量纲。"""
    return [v * std + mean for v in values]
