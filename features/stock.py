# 个股 StockHeat 特征计算
#
# 数据来源: QuestDB daily_bars 表

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from features.utils import (
    ema, sma, percentile_rank_rolling, calculate_returns,
    rolling_max, rolling_min
)
from data import get_questdb_client


@dataclass
class StockHeatResult:
    """个股热度计算结果"""
    # 各因子分数
    rs_score: float  # 个股相对强弱
    rvol_score: float  # 相对量
    pullback_score: float  # 回踩质量
    sector_diffusion_factor: float  # 板块扩散乘子

    # 综合分数
    stock_heat: float

    # 细节
    sr20: float  # 20日相对板块强弱
    sr5: float  # 5日相对板块强弱
    rvol_20: float  # 20日相对量
    recent_high: float  # 20日高点
    depth: float  # 回踩深度
    speed: int  # 回踩速度(bar数)

    # 信号
    breakout_level: str  # 突破位置
    pullback_zone: str  # 回踩区域
    invalidate_level: float  # 失效位置
    stop_price: float  # 止损价
    r_price: float  # 1R 风险


def calculate_stock_heat(
    stock_code: str,
    sector_code: str,
    lookback: int = 252
) -> StockHeatResult:
    """
    计算个股的 StockHeat

    Args:
        stock_code: 股票代码，如 600000.SH
        sector_code: 板块代码，如 TGNAI PC
        lookback: 回看天数

    Returns:
        StockHeatResult
    """
    qdb = get_questdb_client()

    # 1. 获取个股K线
    stock_df = qdb.query_daily_bars(symbol=stock_code, limit=300)
    if stock_df.empty or len(stock_df) < 60:
        return _default_stock_heat()

    # 转换数据类型
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        if col in stock_df.columns:
            stock_df[col] = pd.to_numeric(stock_df[col], errors='coerce')
    stock_df['date'] = pd.to_datetime(stock_df['ts'])
    stock_df = stock_df.sort_values('date').reset_index(drop=True)

    # 2. 获取板块K线（从 QuestDB）
    sector_name = sector_code[3:] if sector_code.startswith('TGN') else sector_code
    try:
        sector_df = qdb.query_concept_bars(concept_name=sector_name, limit=300)
        if not sector_df.empty:
            sector_df = sector_df.rename(columns={'ts': 'date'})
            sector_df['date'] = pd.to_datetime(sector_df['date'])
        else:
            sector_df = None
    except Exception as e:
        print(f"获取板块数据失败: {e}")
        sector_df = None

    # === 1. StockRS（相对强弱）35% ===
    close = stock_df['close']

    # 个股收益率
    sr20 = calculate_returns(close, 20).iloc[-1] if len(close) >= 20 else 0
    sr5 = calculate_returns(close, 5).iloc[-1] if len(close) >= 5 else 0

    # 板块收益率
    if sector_df is not None and len(sector_df) > 0:
        sector_close = sector_df['close']
        sector_ret_20 = calculate_returns(sector_close, 20).iloc[-1] if len(sector_close) >= 20 else 0
        sector_ret_5 = calculate_returns(sector_close, 5).iloc[-1] if len(sector_close) >= 5 else 0
    else:
        sector_ret_20 = 0
        sector_ret_5 = 0

    # 相对强弱
    sr20 = sr20 - sector_ret_20
    sr5 = sr5 - sector_ret_5
    sr_acc = sr5 - sr20

    # 简化分位数
    rs_score = 50 + (sr20 * 500) + (sr_acc * 200)

    # === 2. RVOL（相对量）25% ===
    volume = stock_df['volume']
    vol_ma20 = sma(volume, 20).iloc[-1]
    rvol_20 = volume.iloc[-1] / vol_ma20 if vol_ma20 > 0 else 1
    rvol_score = min(100, rvol_20 * 50)

    # === 3. PullbackQuality（回踩质量）25% ===
    high_20 = rolling_max(close, 20).iloc[-1]
    recent_high = high_20

    # 回踩深度: (close - high) / high
    depth = (close.iloc[-1] - recent_high) / recent_high if recent_high > 0 else 0

    # 回踩速度: 从高点到当前的bar数
    # 简化: 假设最近20天内的最高点出现在哪天
    high_idx = close[:20].idxmax()
    speed = len(close) - high_idx - 1

    # 回踩得分
    # 浅回撤(-2% ~ -6%)得分高
    if -0.06 <= depth <= -0.02:
        pullback_score = 80
    elif -0.10 <= depth < -0.06:
        pullback_score = 60
    elif depth > -0.02:
        pullback_score = 50  # 未回撤
    else:
        pullback_score = 30  # 过深

    # 过快下杀降分
    if speed < 3:
        pullback_score *= 0.8

    # === 4. 板块扩散乘子 15% ===
    # 需要板块扩散度，这里简化用板块热度代替
    # 如果板块扩散低，个股热度封顶
    sector_diffusion_factor = 1.0  # 简化

    # === 综合 StockHeat ===
    stock_heat = (
        0.35 * rs_score +
        0.25 * rvol_score +
        0.25 * pullback_score +
        0.15 * 100 * sector_diffusion_factor
    )

    # 板块扩散低时封顶
    if sector_diffusion_factor < 0.5:
        stock_heat = min(stock_heat, 70)

    # === 信号 ===
    ema20 = ema(close, 20).iloc[-1]
    ema60 = ema(close, 60).iloc[-1] if len(close) >= 60 else ema20

    # 突破位置
    if close.iloc[-1] > high_20:
        breakout_level = "20日高点"
    elif close.iloc[-1] > ema20:
        breakout_level = "EMA20"
    else:
        breakout_level = "EMA60"

    # 回踩区域
    if abs(close.iloc[-1] - ema20) / ema20 < 0.02:
        pullback_zone = "EMA20附近"
    else:
        pullback_zone = "偏离EMA"

    # 失效/止损
    invalidate_level = ema60
    stop_price = close.iloc[-1] * 0.95  # 5%止损简化
    r_price = close.iloc[-1] - stop_price  # 1R = 5%

    return StockHeatResult(
        rs_score=rs_score,
        rvol_score=rvol_score,
        pullback_score=pullback_score,
        sector_diffusion_factor=sector_diffusion_factor,
        stock_heat=stock_heat,
        sr20=sr20,
        sr5=sr5,
        rvol_20=rvol_20,
        recent_high=recent_high,
        depth=depth,
        speed=speed,
        breakout_level=breakout_level,
        pullback_zone=pullback_zone,
        invalidate_level=invalidate_level,
        stop_price=stop_price,
        r_price=r_price
    )


def filter_stocks_by_criteria(
    stock_codes: List[str],
    sector_code: str,
    min_volume: float = 50000000,  # 日均成交额阈值
    require_structure: bool = True
) -> List[str]:
    """
    基础过滤：成交量 + 结构过滤

    数据来源: QuestDB daily_bars 表

    Args:
        stock_codes: 候选股票列表
        sector_code: 板块代码
        min_volume: 最小日均成交额
        require_structure: 是否要求 close > ema20 > ema60

    Returns:
        过滤后的股票列表
    """
    qdb = get_questdb_client()
    valid_stocks = []

    for code in stock_codes:
        try:
            # 从 QuestDB 获取K线数据
            # 数据来源: QuestDB daily_bars 表
            df = qdb.query_daily_bars(symbol=code, limit=60)
            if df is None or df.empty or len(df) < 20:
                continue

            # 转换数据类型
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # 成交量过滤
            avg_amount = df['amount'].iloc[-20:].mean()
            if avg_amount < min_volume:
                continue

            # 结构过滤
            if require_structure:
                close = df['close'].sort_index() if 'ts' in df.columns else df['close']
                ema20_val = ema(close, 20).iloc[-1]
                ema60_val = ema(close, 60).iloc[-1] if len(close) >= 60 else ema20_val

                if not (close.iloc[-1] > ema20_val > ema60_val):
                    continue

            valid_stocks.append(code)

        except Exception as e:
            print(f"过滤股票 {code} 失败: {e}")
            continue

    return valid_stocks


def calculate_stocks_heat(
    stock_codes: List[str],
    sector_code: str
) -> List[StockHeatResult]:
    """
    批量计算多只股票的 StockHeat

    Args:
        stock_codes: 股票代码列表
        sector_code: 板块代码

    Returns:
        List[StockHeatResult], 按热度排序
    """
    results = []

    for code in stock_codes:
        try:
            result = calculate_stock_heat(code, sector_code)
            results.append(result)
        except Exception as e:
            print(f"计算 {code} 热度失败: {e}")
            continue

    # 按热度排序
    results.sort(key=lambda x: x.stock_heat, reverse=True)
    return results


def _default_stock_heat() -> StockHeatResult:
    """默认值"""
    return StockHeatResult(
        rs_score=50,
        rvol_score=50,
        pullback_score=50,
        sector_diffusion_factor=1.0,
        stock_heat=50,
        sr20=0,
        sr5=0,
        rvol_20=1.0,
        recent_high=0,
        depth=0,
        speed=0,
        breakout_level="未知",
        pullback_zone="未知",
        invalidate_level=0,
        stop_price=0,
        r_price=0
    )
