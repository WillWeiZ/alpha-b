# 板块 SectorHeat 特征计算
#
# 数据来源:
# - 板块K线: QuestDB concept_bars 表
# - 成分股: QuestDB concept_constituents 表
# - 个股K线: QuestDB daily_bars 表

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from features.utils import (
    ema, sma, percentile_rank_rolling, calculate_returns,
    rolling_max
)
from data import get_questdb_client


# 扩散度计算缓存（避免重复查询）
_diffusion_cache: Dict[str, Tuple[float, float, float, int]] = {}


def calculate_diffusion_metrics(
    sector_name: str,
    stock_codes: List[str],
    lookback: int = 20,
    use_cache: bool = True
) -> Tuple[float, float, float, int]:
    """
    计算板块扩散度指标（真实计算）

    Args:
        sector_name: 板块名称
        stock_codes: 成分股代码列表
        lookback: 回看天数
        use_cache: 是否使用缓存

    Returns:
        (diff_up, diff_ma, diff_high, valid_count):
        - diff_up: 上涨成分股占比 (0-100)
        - diff_ma: EMA20上成分股占比 (0-100)
        - diff_high: 创20日新高成分股占比 (0-100)
        - valid_count: 有效成分股数量
    """
    global _diffusion_cache

    cache_key = f"{sector_name}_{len(stock_codes)}"
    if use_cache and cache_key in _diffusion_cache:
        return _diffusion_cache[cache_key]

    qdb = get_questdb_client()

    up_count = 0      # 上涨
    ma_count = 0     # EMA20上
    high_count = 0   # 20日新高
    valid_count = 0

    # 限制最大查询数量（性能考虑）
    max_stocks = min(len(stock_codes), 50)

    for stock_code in stock_codes[:max_stocks]:
        try:
            # 获取个股K线
            df = qdb.query_daily_bars(symbol=stock_code, limit=lookback + 10)
            if df is None or df.empty or len(df) < lookback:
                continue

            # 转换数据类型
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            df = df.sort_values('ts').reset_index(drop=True)

            close = df['close']
            high = df['high']

            if len(close) < lookback:
                continue

            valid_count += 1

            # diff_up: 当日是否上涨
            ret_today = (close.iloc[-1] / close.iloc[-2] - 1) if len(close) >= 2 else 0
            if ret_today > 0:
                up_count += 1

            # diff_ma: 收盘价是否 > EMA20
            ema20_val = ema(close, 20).iloc[-1]
            if close.iloc[-1] > ema20_val:
                ma_count += 1

            # diff_high: 是否创20日新高
            high_20 = rolling_max(high, lookback).iloc[-1]
            if close.iloc[-1] >= high_20 * 0.99:  # 允许微小误差
                high_count += 1

        except Exception as e:
            continue

    # 计算百分比
    if valid_count > 0:
        diff_up = (up_count / valid_count) * 100
        diff_ma = (ma_count / valid_count) * 100
        diff_high = (high_count / valid_count) * 100
    else:
        diff_up = 50.0
        diff_ma = 50.0
        diff_high = 50.0

    # 缓存结果
    if use_cache:
        _diffusion_cache[cache_key] = (diff_up, diff_ma, diff_high, valid_count)

    return diff_up, diff_ma, diff_high, valid_count


def clear_diffusion_cache():
    """清除扩散度缓存"""
    global _diffusion_cache
    _diffusion_cache = {}


@dataclass
class SectorHeatResult:
    """板块热度计算结果"""
    # 各因子分数
    rs_score: float  # 相对强弱
    diffusion_score: float  # 扩散度
    participation_score: float  # 参与度

    # 综合分数
    sector_heat: float

    # 排名
    sector_rank: float  # 0-100, 前20%为候选

    # 轮动信号
    is_candidate: bool  # 是否为轮动候选
    consecutive_days: int  # 连续保持高热度天数

    # 细节
    rs20: float  # 20日相对强弱
    rs5: float  # 5日相对强弱
    diff_up: float  # 上涨成分股占比
    diff_ma: float  # EMA20上成分股占比
    diff_high: float  # 创20日新高成分股占比
    sector_volume_percentile: float  # 成交量分位


def calculate_sector_heat(
    sector_code: str,
    market_bars: Optional[pd.DataFrame] = None,
    lookback: int = 252,
    use_real_diffusion: bool = True
) -> SectorHeatResult:
    """
    计算单个板块的 SectorHeat

    Args:
        sector_code: QMT板块代码，如 "TGNAI PC"
                       或者同花顺名称，如 "AI PC"
        market_bars: 基准指数K线（如沪深300），用于计算相对强弱
        lookback: 回看天数
        use_real_diffusion: 是否使用真实扩散度计算（遍历成分股），
                           False 时使用简化计算（性能更快但精度低）

    Returns:
        SectorHeatResult
    """
    qdb = get_questdb_client()

    # 映射 QMT -> 同花顺
    # TGNAI PC -> AI PC
    if sector_code.startswith("TGN"):
        sector_name = sector_code[3:]  # 去掉 TGN 前缀
    else:
        sector_name = sector_code

    # 1. 获取板块K线（从 QuestDB）
    try:
        sector_bars = qdb.query_concept_bars(concept_name=sector_name, limit=300)
    except Exception as e:
        print(f"获取板块 {sector_name} 失败: {e}")
        return _default_sector_heat()

    if sector_bars is None or sector_bars.empty or len(sector_bars) < 20:
        return _default_sector_heat()

    # 转换数据类型
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        if col in sector_bars.columns:
            sector_bars[col] = pd.to_numeric(sector_bars[col], errors='coerce')

    sector_bars = sector_bars.rename(columns={'ts': 'date'})
    sector_bars['date'] = pd.to_datetime(sector_bars['date'])
    sector_bars = sector_bars.sort_values('date').reset_index(drop=True)
    close = sector_bars['close']

    # 2. 获取基准指数K线（默认用上证指数）
    if market_bars is None:
        market_bars = qdb.query_daily_bars(symbol='000001.SH', limit=300)
        if not market_bars.empty:
            market_bars['close'] = pd.to_numeric(market_bars['close'], errors='coerce')
            market_bars = market_bars.rename(columns={'ts': 'date'})
            market_bars['date'] = pd.to_datetime(market_bars['date'])

    # === 1. RSScore（相对强弱）40% ===
    # 计算板块收益率
    sector_ret_20 = calculate_returns(close, 20).iloc[-1] if len(close) >= 20 else 0
    sector_ret_5 = calculate_returns(close, 5).iloc[-1] if len(close) >= 5 else 0

    # 基准收益率
    if market_bars is not None and len(market_bars) > 0:
        market_close = market_bars['close']
        market_ret_20 = calculate_returns(market_close, 20).iloc[-1] if len(market_close) >= 20 else 0
        market_ret_5 = calculate_returns(market_close, 5).iloc[-1] if len(market_close) >= 5 else 0
    else:
        market_ret_20 = 0
        market_ret_5 = 0

    rs20 = sector_ret_20 - market_ret_20
    rs5 = sector_ret_5 - market_ret_5
    rs_acc = rs5 - rs20

    # 分位数（简化版：直接用收益率排名）
    # 实际应该用历史分位数，这里用简化公式
    rs_score = 50 + (rs20 * 500) + (rs_acc * 200)  # 简化

    # === 2. DiffusionScore（扩散度）40% ===
    # 获取成分股数据（从 QuestDB）
    try:
        constituents = qdb.query_concept_constituents(concept_name=sector_name)
        stock_codes = constituents['symbol'].tolist() if not constituents.empty else []
    except Exception as e:
        print(f"获取成分股失败: {e}")
        stock_codes = []

    # 过滤沪深A股
    stock_codes = [s for s in stock_codes if s.endswith('.SH') or s.endswith('.SZ')]

    if len(stock_codes) > 0 and use_real_diffusion:
        # 使用真实的扩散度计算（遍历成分股）
        diff_up, diff_ma, diff_high, valid_count = calculate_diffusion_metrics(
            sector_name, stock_codes, lookback=20, use_cache=True
        )
    else:
        # 简化计算：用板块本身的涨跌代替成分股扩散度
        ret = calculate_returns(close, 1).iloc[-1] if len(close) > 0 else 0
        diff_up = 50 + ret * 500
        diff_ma = 50
        diff_high = 50
        valid_count = 0

    diffusion_score = 0.4 * diff_up + 0.35 * diff_ma + 0.25 * diff_high

    # === 3. ParticipationScore（参与度）20% ===
    if 'volume' in sector_bars.columns:
        volume = sector_bars['volume']
        vol_ma20 = sma(volume, 20).iloc[-1]
        rvol = volume.iloc[-1] / vol_ma20 if vol_ma20 > 0 else 1

        # 简化分位数
        sector_volume_percentile = min(100, rvol * 50)
        participation_score = 0.6 * sector_volume_percentile + 0.4 * min(100, rvol * 50)
    else:
        sector_volume_percentile = 50
        participation_score = 50

    # === 综合 SectorHeat ===
    sector_heat = (
        0.4 * rs_score +
        0.4 * diffusion_score +
        0.2 * participation_score
    )

    # === 排名与候选 ===
    sector_rank = sector_heat  # 简化：直接用热度作为排名
    is_candidate = sector_rank >= 80 and diffusion_score >= 50
    consecutive_days = 2 if is_candidate else 0  # 简化

    return SectorHeatResult(
        rs_score=rs_score,
        diffusion_score=diffusion_score,
        participation_score=participation_score,
        sector_heat=sector_heat,
        sector_rank=sector_rank,
        is_candidate=is_candidate,
        consecutive_days=consecutive_days,
        rs20=rs20,
        rs5=rs5,
        diff_up=diff_up,
        diff_ma=diff_ma,
        diff_high=diff_high,
        sector_volume_percentile=sector_volume_percentile
    )


def calculate_all_sectors_heat(
    market_bars: Optional[pd.DataFrame] = None,
    top_n: int = 20
) -> List[SectorHeatResult]:
    """
    计算所有概念板块的热度

    Args:
        market_bars: 基准指数K线
        top_n: 返回前N个候选板块

    Returns:
        List[SectorHeatResult], 按热度排序
    """
    qdb = get_questdb_client()

    # 获取概念板块列表（从 QuestDB）
    # 数据来源: QuestDB concept_constituents 表
    concepts = qdb.get_concept_list()

    results = []
    for i, concept in enumerate(concepts):
        if i % 50 == 0:
            print(f"进度: {i}/{len(concepts)}")
        result = calculate_sector_heat(concept, market_bars)
        results.append(result)

    # 按热度排序
    results.sort(key=lambda x: x.sector_heat, reverse=True)

    return results[:top_n]


def _default_sector_heat() -> SectorHeatResult:
    """默认值"""
    return SectorHeatResult(
        rs_score=50,
        diffusion_score=50,
        participation_score=50,
        sector_heat=50,
        sector_rank=50,
        is_candidate=False,
        consecutive_days=0,
        rs20=0,
        rs5=0,
        diff_up=50,
        diff_ma=50,
        diff_high=50,
        sector_volume_percentile=50
    )
