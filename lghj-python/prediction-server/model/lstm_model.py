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


# ---------------------------------------------------------------------------
# 预测后处理（推理侧的"逻辑优化"，不改变模型权重与训练流程）
# ---------------------------------------------------------------------------
def anchor_to_last_price(pred_prices: list, last_real_price: float) -> list:
    """
    锚定修正：消除"预测首日相对最新真实价的跳空偏离"。

    问题背景：
        逐窗口 z-score 归一化下，模型预测值经反归一化后，首日常与窗口最后一日
        真实价存在 1% 左右的系统性偏离（实测茅台 -1.05%）。若直接拼接，前端
        K 线图上历史末点与预测首日之间会出现"跳空缺口"，视觉与逻辑上都不连续。

    做法：
        计算偏移量 delta = 首日预测 - 最新真实价，并对整条预测序列做**等量平移**
        （平移而非缩放，保留模型预测出的形态与斜率），使首日严格等于最新真实价。
        平移后最低价若跌破 0（极端情况），改为等比缩放兜底。

    返回平移后的价格列表（长度不变）。
    """
    if not pred_prices:
        return pred_prices
    delta = float(pred_prices[0]) - float(last_real_price)
    shifted = [float(p) - delta for p in pred_prices]
    # 极端兜底：平移后出现非正价格则退化为等比缩放
    if min(shifted) <= 0:
        ratio = float(last_real_price) / float(pred_prices[0])
        shifted = [float(p) * ratio for p in pred_prices]
    return shifted


def rescale_volatility(pred_prices: list, last_real_price: float,
                       hist_std: float, seq_len: int,
                       vol_ratio: float = 0.5) -> list:
    """
    波动率重标定：缓解"预测曲线被压成近似直线"的问题。

    问题背景：
        模型以 MSE 为损失，在归一化空间中会向条件均值收敛，导致预测序列的
        标准差远小于真实历史波动（实测 30 日预测极差 1.13% vs 真实 60 日 12.09%，
        波动被压缩约 10.7 倍），曲线近乎水平直线，失去参考意义。

    做法：
        以"历史窗口标准差 vs 预测序列标准差"的比值为基础，按 vol_ratio 比例
        把预测序列的波动放大回来（部分修正，避免过度放大噪声）：
            target_std = hist_std * min(放大比, 上限)
            pred' = mean(pred) + (pred - mean(pred)) * (target_std / std(pred))
        再整体平移使首日仍锚定最新真实价（与本函数组合使用）。

    参数：
        pred_prices     已锚定的预测价格序列
        last_real_price 最新真实收盘价
        hist_std        输入窗口（最近 seq_len 日）的收盘价标准差
        seq_len         窗口长度（用于把 30 日预测波动折算到可比尺度）
        vol_ratio       波动恢复强度 0~1（默认 0.5 = 恢复一半，保守取值）

    返回重标定后的价格列表（长度不变）。
    """
    import statistics

    if not pred_prices or len(pred_prices) < 2:
        return pred_prices
    pred_std = statistics.pstdev(pred_prices)
    if pred_std < 1e-9:
        return pred_prices

    # 预测跨度与历史窗口的尺度折算：30 日预测对比 60 日窗口，波动按 sqrt(天数) 缩放
    horizon_scale = (len(pred_prices) / max(seq_len, 1)) ** 0.5
    expected_std = float(hist_std) * horizon_scale
    if expected_std <= pred_std:
        return pred_prices  # 模型波动已足够大，不放大

    # 按 vol_ratio 做部分修正（保守，避免把噪声也放大）
    target_std = pred_std + (expected_std - pred_std) * float(vol_ratio)
    # 放大上限：不超过预测序列标准差的 4 倍，防止极端行情下失真
    target_std = min(target_std, pred_std * 4.0)

    mean_pred = sum(pred_prices) / len(pred_prices)
    k = target_std / pred_std
    scaled = [mean_pred + (float(p) - mean_pred) * k for p in pred_prices]
    # 重新锚定首日
    delta = scaled[0] - float(last_real_price)
    return [p - delta for p in scaled]


def smooth_predictions(pred_prices: list, alpha: float = 0.25) -> list:
    """
    轻度指数平滑：降低预测序列的逐日抖动，提升视觉可读性。

    对逐日预测做单向 EMA（alpha 越大越贴近原值），仅用于展示序列，
    不改变首日（已锚定）与整体趋势方向。
    """
    if not pred_prices or len(pred_prices) < 3:
        return pred_prices
    out = [float(pred_prices[0])]
    for p in pred_prices[1:]:
        out.append(out[-1] + float(alpha) * (float(p) - out[-1]))
    return out

