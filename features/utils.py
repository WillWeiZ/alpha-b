# 特征计算工具函数

import numpy as np
import pandas as pd
from typing import Optional, List


def ema(series: pd.Series, n: int) -> pd.Series:
    """EMA 计算"""
    return series.ewm(span=n, adjust=False).mean()


def sma(series: pd.Series, n: int) -> pd.Series:
    """SMA (简单移动平均)"""
    return series.rolling(window=n).mean()


def rsi(series: pd.Series, n: int = 14) -> pd.Series:
    """RSI 计算"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=n).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=n).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def percentile_rank(series: pd.Series, lookback: int = 252) -> pd.Series:
    """分位数映射到 0-100"""
    def _rank(x):
        if pd.isna(x) or x.isnull().all():
            return np.nan
        window = series.tail(lookback)
        if len(window) == 0:
            return 50.0
        # 计算当前值在历史窗口的排名
        rank = (window < x).sum() / len(window) * 100
        return rank

    return series.apply(_rank)


def percentile_rank_rolling(series: pd.Series, lookback: int = 252) -> pd.Series:
    """
    滚动分位数
    返回 0-100，表示当前值在过去 lookback 天的百分比排名
    使用 pandas 内置 rank 方法
    """
    def _rank_window(x):
        """对窗口内的值计算百分比排名"""
        if len(x) < lookback:
            return 50.0
        # rank(pct=True) 返回 0-1，乘以 100 变成 0-100
        return pd.Series(x).rank(pct=True).iloc[-1] * 100

    result = series.rolling(window=lookback, min_periods=lookback).apply(
        _rank_window, raw=False
    )
    # 前面不够 lookback 天的用 50 填充
    result = result.fillna(50)
    return result


def winsorize(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    """去极值（winsorize）"""
    q_low = series.quantile(lower)
    q_high = series.quantile(upper)
    return series.clip(lower=q_low, upper=q_high)


def normalize(series: pd.Series, min_val: float = 0, max_val: float = 100) -> pd.Series:
    """归一化到 [min_val, max_val]"""
    s_min = series.min()
    s_max = series.max()
    if s_max == s_min:
        return pd.Series(min_val, index=series.index)
    return (series - s_min) / (s_max - s_min) * (max_val - min_val) + min_val


def rolling_max(series: pd.Series, window: int) -> pd.Series:
    """滚动最大值"""
    return series.rolling(window=window).max()


def rolling_min(series: pd.Series, window: int) -> pd.Series:
    """滚动最小值"""
    return series.rolling(window=window).min()


def bars_since_condition(series: pd.Series, condition: pd.Series) -> pd.Series:
    """计算满足条件以来的 bar 数"""
    result = pd.Series(np.nan, index=series.index)
    count = 0
    for i in range(len(series)):
        if condition.iloc[i]:
            count = 0
        else:
            count += 1
        result.iloc[i] = count
    return result


def safe_divide(a: pd.Series, b: pd.Series, fill_value: float = 0.0) -> pd.Series:
    """安全除法"""
    return a / b.replace(0, np.nan).fillna(fill_value)


def calculate_returns(close: pd.Series, n: int = 1) -> pd.Series:
    """计算收益率"""
    return close / close.shift(n) - 1


def rank_within(series: pd.Series, lookback: int) -> pd.Series:
    """滚动窗口内排名归一化到 0-100"""
    result = pd.Series(np.nan, index=series.index)
    for i in range(lookback - 1, len(series)):
        window = series.iloc[i - lookback + 1:i + 1]
        current = series.iloc[i]
        result.iloc[i] = (window < current).sum() / lookback * 100
    return result


def map_to_7state(score: float) -> str:
    """将分数映射到 7 态"""
    if score < 10:
        return "冻"
    elif score < 25:
        return "寒"
    elif score < 40:
        return "凉"
    elif score < 60:
        return "平"
    elif score < 75:
        return "温"
    elif score < 90:
        return "热"
    else:
        return "沸"
