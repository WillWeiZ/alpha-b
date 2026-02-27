# 大盘 MarketHeat 特征计算
#
# 数据来源: QuestDB index_bars 表, daily_bars 表

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from features.utils import (
    ema, sma, percentile_rank_rolling, winsorize,
    calculate_returns, normalize, map_to_7state,
    calculate_limit_prices
)
from data import get_questdb_client


# 市场广度缓存
_market_breadth_cache: Dict[str, Dict[str, int]] = {}


def calculate_market_breadth(trade_date: str = None, use_cache: bool = True) -> Dict[str, int]:
    """
    计算市场广度数据（从 daily_bars 推算）

    Args:
        trade_date: 交易日期 (YYYYMMDD格式)，默认为最新交易日
        use_cache: 是否使用缓存

    Returns:
        {
            'up_count': 上涨家数,
            'down_count': 下跌家数,
            'limit_up_count': 涨停家数,
            'limit_down_count': 跌停家数,
            'total_count': 总家数,
            'trade_date': 交易日期
        }
    """
    global _market_breadth_cache

    if trade_date is None:
        # 获取最新交易日期
        qdb = get_questdb_client()
        result = qdb.execute("SELECT max(ts) FROM daily_bars")
        if result is not None and not result.empty:
            max_ts = result.iloc[0, 0]
            if max_ts:
                trade_date = str(max_ts)[:10].replace('-', '')

    if not trade_date:
        trade_date = datetime.now().strftime('%Y%m%d')

    cache_key = trade_date
    if use_cache and cache_key in _market_breadth_cache:
        return _market_breadth_cache[cache_key]

    qdb = get_questdb_client()

    # 解析交易日期
    dt = datetime.strptime(trade_date, '%Y%m%d')
    date_str = dt.strftime('%Y-%m-%d')
    next_dt = dt + timedelta(days=1)
    next_date_str = next_dt.strftime('%Y-%m-%d')

    # 获取当日的行情数据
    query = f"""
    SELECT symbol, close, open
    FROM daily_bars
    WHERE ts >= '{date_str}'
    AND ts < '{next_date_str}'
    """
    df = qdb.execute(query)

    # 如果当日没有数据，尝试获取前一天的数据
    if df is None or df.empty:
        dt = dt - timedelta(days=1)
        date_str = dt.strftime('%Y-%m-%d')
        next_dt = dt + timedelta(days=1)
        next_date_str = next_dt.strftime('%Y-%m-%d')
        query = f"""
        SELECT symbol, close, open
        FROM daily_bars
        WHERE ts >= '{date_str}'
        AND ts < '{next_date_str}'
        """
        df = qdb.execute(query)

        if df is None or df.empty:
            # 回退：使用 open 作为前收盘价的近似
            return _market_breadth_cache.get(cache_key, {
                'up_count': 0, 'down_count': 0,
                'limit_up_count': 0, 'limit_down_count': 0,
                'total_count': 0, 'trade_date': trade_date
            })

    # 获取前一天的收盘价
    dt = datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=1)
    prev_date_str = dt.strftime('%Y-%m-%d')
    prev_next_dt = dt + timedelta(days=1)
    prev_next_date_str = prev_next_dt.strftime('%Y-%m-%d')

    prev_query = f"""
    SELECT symbol, close as pre_close
    FROM daily_bars
    WHERE ts >= '{prev_date_str}'
    AND ts < '{prev_next_date_str}'
    """
    prev_df = qdb.execute(prev_query)

    # 创建前收盘价映射
    pre_close_map = {}
    if prev_df is not None and not prev_df.empty:
        for _, row in prev_df.iterrows():
            pre_close_map[row['symbol']] = row['pre_close']

    # 统计涨跌停
    up_count = 0
    down_count = 0
    limit_up_count = 0
    limit_down_count = 0

    for _, row in df.iterrows():
        symbol = row['symbol']
        close = row.get('close')
        open_price = row.get('open', close)

        if pd.isna(close) or pd.isna(open_price):
            continue

        # 获取前收盘价
        pre_close = pre_close_map.get(symbol, open_price)
        if pd.isna(pre_close) or pre_close <= 0:
            pre_close = open_price  # 使用开盘价作为近似

        # 计算涨跌幅
        change_pct = (close - pre_close) / pre_close * 100 if pre_close > 0 else 0

        # 判断涨跌
        if change_pct > 0:
            up_count += 1
        elif change_pct < 0:
            down_count += 1

        # 判断涨跌停（使用精确计算）
        limit_up, limit_down = calculate_limit_prices(symbol, pre_close, trade_date)
        if limit_up and close >= limit_up:
            limit_up_count += 1
        if limit_down and close <= limit_down:
            limit_down_count += 1

    total_count = up_count + down_count

    result = {
        'up_count': up_count,
        'down_count': down_count,
        'limit_up_count': limit_up_count,
        'limit_down_count': limit_down_count,
        'total_count': total_count,
        'trade_date': trade_date
    }

    if use_cache:
        _market_breadth_cache[cache_key] = result

    return result


def get_market_breadth_for_date(trade_date: str) -> Dict[str, int]:
    """
    获取指定日期的市场广度（清除缓存强制重新计算）

    Args:
        trade_date: 交易日期 (YYYYMMDD格式)

    Returns:
        市场广度数据字典
    """
    global _market_breadth_cache
    # 清除该日期的缓存
    _market_breadth_cache.pop(trade_date, None)
    return calculate_market_breadth(trade_date, use_cache=False)


def clear_market_breadth_cache():
    """清除市场广度缓存"""
    global _market_breadth_cache
    _market_breadth_cache = {}


@dataclass
class MarketHeatResult:
    """MarketHeat 计算结果"""
    # 原始分数
    trend_score: float
    breadth_score: float
    extremes_score: float
    liquidity_score: float

    # 综合分数
    market_heat: float

    # 7态
    market_state_7: str

    # 风险模式
    risk_mode: str  # SAFE / CAUTIOUS / AGGRESSIVE

    # 细节
    trend_1: int  # 结构多头信号
    trend_2: float  # 20日收益率分位
    trend_3: float  # EMA差值分位
    adv_ratio: float  # 上涨家数比
    limit_spread: int  # 涨停-跌停家数
    liq_score: float  # 流动性分数
    liq_acc: float  # 流动性加速


def calculate_market_heat(
    market_bars: pd.DataFrame,
    market_breadth: Optional[pd.DataFrame] = None,
    lookback: int = 252,
    trade_date: str = None
) -> MarketHeatResult:
    """
    计算 MarketHeat 大盘热度

    Args:
        market_bars: 大盘指数K线，包含 open/high/low/close/volume
        market_breadth: 市场广度数据 (up_count, down_count, limit_up_count, limit_down_count)
                       如果为 None，将从 daily_bars 自动计算
        lookback: 回看天数
        trade_date: 交易日期 (YYYYMMDD格式)，用于计算市场广度

    Returns:
        MarketHeatResult
    """
    if market_bars is not None and len(market_bars) < 60:
        # 数据不够，返回默认值
        return _default_market_heat()

    # 如果没有提供市场广度数据，自动计算
    if market_breadth is None:
        breadth_data = calculate_market_breadth(trade_date)
        up_count = breadth_data.get('up_count', 0)
        down_count = breadth_data.get('down_count', 0)
        limit_up = breadth_data.get('limit_up_count', 0)
        limit_down = breadth_data.get('limit_down_count', 0)
    elif isinstance(market_breadth, dict):
        # 传入的是字典格式
        up_count = market_breadth.get('up_count', 0)
        down_count = market_breadth.get('down_count', 0)
        limit_up = market_breadth.get('limit_up_count', 0)
        limit_down = market_breadth.get('limit_down_count', 0)
    else:
        # 传入的是 DataFrame 格式（兼容旧代码）
        up_count = market_breadth["up_count"].iloc[-1] if "up_count" in market_breadth.columns else 0
        down_count = market_breadth["down_count"].iloc[-1] if "down_count" in market_breadth.columns else 0
        limit_up = market_breadth.get("limit_up_count", pd.Series([0])).iloc[-1]
        limit_down = market_breadth.get("limit_down_count", pd.Series([0])).iloc[-1]

    # 如果没有 market_bars，创建空数据框用于后续计算
    if market_bars is None or len(market_bars) == 0:
        close = pd.Series([0])
        open_price = pd.Series([0])
        high = pd.Series([0])
        low = pd.Series([0])
        volume = pd.Series([0])
    else:
        close = market_bars["close"]
        open_price = market_bars["open"]
        high = market_bars["high"]
        low = market_bars["low"]
        volume = market_bars["volume"]

    # === 1. TrendScore（趋势结构）40% ===
    ema20 = ema(close, 20)
    ema60 = ema(close, 60)

    # trend_1: 多头结构 (close > ema20 > ema60)
    trend_1 = ((close > ema20) & (ema20 > ema60)).astype(int).iloc[-1]

    # trend_2: 20日收益率分位
    ret_20 = calculate_returns(close, 20)
    trend_2 = percentile_rank_rolling(ret_20, lookback).iloc[-1]

    # trend_3: EMA 差值分位
    ema_diff = ema20 - ema60
    trend_3 = percentile_rank_rolling(ema_diff, lookback).iloc[-1]

    # TrendScore 合成 (归一化到 0-100)
    trend_score = (40 * trend_1 + 30 * trend_2 / 100 + 30 * trend_3 / 100)

    # === 2. BreadthScore（赚钱效应）35% ===
    # 上涨家数比
    total = up_count + down_count
    adv_ratio = up_count / total if total > 0 else 0.5

    # 涨跌停差
    limit_spread = limit_up - limit_down

    # BreadthScore 合成 (归一化到 0-100)
    # 40% * adv_ratio分位 + 30% * limit_spread分位 + 30% * 分布得分(默认50)
    # 简化：直接用 adv_ratio * 40 + min(limit_spread/50*30, 30) + 15
    limit_spread_clipped = max(-50, min(50, limit_spread))  # 限制在 -50 到 50
    breadth_score = (
        40 * adv_ratio +
        30 * (50 + limit_spread_clipped) / 100 +  # 映射到 0-30
        30 * 0.5  # 分布得分默认50/100
    )

    # === 3. ExtremesScore（极端结构）25% ===
    # 70% * limit_spread分位 + 30% * 连板高度分位(默认50)
    extremes_score = 70 * (50 + limit_spread_clipped) / 100 + 30 * 0.5

    # === 4. LiquidityScore（参与度）15% ===
    # 需要市场总成交量，这里用大盘成交量代替
    if market_bars is not None and "total_volume" in market_bars.columns:
        total_vol = market_bars["total_volume"]
    else:
        total_vol = volume

    # 成交量分位
    vol_ma20 = sma(total_vol, 20)
    rvol = total_vol / vol_ma20

    liq_score = percentile_rank_rolling(total_vol, lookback).iloc[-1]
    liq_acc = percentile_rank_rolling(rvol, lookback).iloc[-1]

    # LiquidityScore 合成 (60% * 成交量分位 + 40% * 放量分位)
    liquidity_score = 0.6 * liq_score + 0.4 * liq_acc

    # === 综合 MarketHeat ===
    market_heat = (
        0.25 * trend_score +
        0.35 * breadth_score +
        0.25 * extremes_score +
        0.15 * liquidity_score
    )

    # 7态映射
    market_state_7 = map_to_7state(market_heat)

    # 风险模式
    risk_mode = _calculate_risk_mode(market_heat, trend_1, limit_spread)

    return MarketHeatResult(
        trend_score=trend_score,
        breadth_score=breadth_score,
        extremes_score=extremes_score,
        liquidity_score=liquidity_score,
        market_heat=market_heat,
        market_state_7=market_state_7,
        risk_mode=risk_mode,
        trend_1=trend_1,
        trend_2=trend_2,
        trend_3=trend_3,
        adv_ratio=adv_ratio,
        limit_spread=limit_spread,
        liq_score=liq_score,
        liq_acc=liq_acc
    )


def _calculate_risk_mode(market_heat: float, trend_1: int, limit_spread: int) -> str:
    """计算风险模式"""
    if market_heat < 25 or limit_spread < -10:
        return "SAFE"
    elif market_heat < 50 or trend_1 == 0:
        return "CAUTIOUS"
    else:
        return "AGGRESSIVE"


def _default_market_heat() -> MarketHeatResult:
    """默认值"""
    return MarketHeatResult(
        trend_score=50,
        breadth_score=50,
        extremes_score=50,
        liquidity_score=50,
        market_heat=50,
        market_state_7="平",
        risk_mode="CAUTIOUS",
        trend_1=0,
        trend_2=50,
        trend_3=50,
        adv_ratio=0.5,
        limit_spread=0,
        liq_score=50,
        liq_acc=50
    )


# === 多指数并行计算 ===

def calculate_multi_index_heat(
    bars_dict: Dict[str, pd.DataFrame],
    market_breadth: Optional[pd.DataFrame] = None
) -> Dict[str, MarketHeatResult]:
    """
    计算多个指数的 MarketHeat

    Args:
        bars_dict: {指数代码: K线DataFrame}
        market_breadth: 市场广度数据

    Returns:
        {指数代码: MarketHeatResult}
    """
    results = {}
    for code, bars in bars_dict.items():
        if bars is not None and len(bars) > 0:
            results[code] = calculate_market_heat(bars, market_breadth)
    return results


def get_composite_market_heat(
    index_heats: Dict[str, MarketHeatResult],
    weights: Optional[Dict[str, float]] = None
) -> MarketHeatResult:
    """
    合成多指数的 MarketHeat（取平均或加权平均）
    """
    if not index_heats:
        return _default_market_heat()

    # 默认权重：沪深300 40%, 中证1000 30%, 上证 30%
    if weights is None:
        weights = {
            "000300.SH": 0.4,  # 沪深300
            "000852.SH": 0.3,  # 中证1000
            "000001.SH": 0.3   # 上证指数
        }

    # 过滤存在的指数
    valid_weights = {k: v for k, v in weights.items() if k in index_heats}
    if not valid_weights:
        return _default_market_heat()

    # 归一化权重
    total = sum(valid_weights.values())
    valid_weights = {k: v / total for k, v in valid_weights.items()}

    # 加权平均
    composite_heat = sum(
        index_heats[k].market_heat * w
        for k, w in valid_weights.items()
    )

    # 7态映射
    market_state_7 = map_to_7state(composite_heat)

    # 风险模式：取最保守的
    risk_modes = [index_heats[k].risk_mode for k in valid_weights.keys()]
    if "SAFE" in risk_modes:
        risk_mode = "SAFE"
    elif "CAUTIOUS" in risk_modes:
        risk_mode = "CAUTIOUS"
    else:
        risk_mode = "AGGRESSIVE"

    return MarketHeatResult(
        trend_score=sum(index_heats[k].trend_score * w for k, w in valid_weights.items()),
        breadth_score=sum(index_heats[k].breadth_score * w for k, w in valid_weights.items()),
        extremes_score=sum(index_heats[k].extremes_score * w for k, w in valid_weights.items()),
        liquidity_score=sum(index_heats[k].liquidity_score * w for k, w in valid_weights.items()),
        market_heat=composite_heat,
        market_state_7=market_state_7,
        risk_mode=risk_mode,
        trend_1=max(index_heats[k].trend_1 for k in valid_weights.keys()),
        trend_2=sum(index_heats[k].trend_2 * w for k, w in valid_weights.items()),
        trend_3=sum(index_heats[k].trend_3 * w for k, w in valid_weights.items()),
        adv_ratio=sum(index_heats[k].adv_ratio * w for k, w in valid_weights.items()),
        limit_spread=sum(index_heats[k].limit_spread * w for k, w in valid_weights.items()),
        liq_score=sum(index_heats[k].liq_score * w for k, w in valid_weights.items()),
        liq_acc=sum(index_heats[k].liq_acc * w for k, w in valid_weights.items())
    )
