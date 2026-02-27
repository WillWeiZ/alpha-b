# 信号引擎 - Auction Gate (T0 09:25 集合竞价)
#
# 数据来源说明:
# - 历史K线数据: QuestDB (index_bars, concept_bars, daily_bars)
# - 实时快照数据: QMT Gateway (get_snapshot) - 需要实时行情

import json
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import get_qmt_client


@dataclass
class AuctionGateSignal:
    """集合竞价闸门信号"""
    run_id: str
    trade_date: str
    timestamp: str
    market_gate: Dict[str, Any]  # 市场闸门
    sector_gates: List[Dict[str, Any]]  # 板块闸门
    stock_gates: List[Dict[str, Any]]  # 个股闸门
    permission_overrides: Dict[str, Any]  # 权限覆盖


def get_auction_data(symbol: str) -> Dict[str, Any]:
    """
    获取集合竞价数据

    从快照数据中估算竞价涨跌幅和竞价量
    实际需要从专门接口获取

    注意: 此函数使用 QMT Gateway 获取实时快照数据
    数据来源: QMT Gateway get_snapshot() - 实时数据
    """
    qmt = get_qmt_client()

    try:
        snapshot = qmt.get_snapshot([symbol])
        if symbol in snapshot:
            data = snapshot[symbol]
            # 竞价数据需要专门接口，这里用昨日收盘价估算
            # 实际应该用: 竞价涨跌幅, 竞价量
            return {
                "symbol": symbol,
                "prev_close": data.get("prev_close", 0),
                "last_price": data.get("last_price", 0),
                "volume": data.get("volume", 0),
            }
    except Exception as e:
        print(f"获取{symbol}快照失败: {e}")

    return {
        "symbol": symbol,
        "prev_close": 0,
        "last_price": 0,
        "volume": 0,
    }


def calculate_market_gate(market_chg: float, market_vol_ratio: float) -> Dict[str, Any]:
    """
    计算市场闸门

    Args:
        market_chg: 市场竞价涨跌幅 (%)
        market_vol_ratio: 竞价量相对历史均量

    Returns:
        gate: RED/YELLOW/GREEN
    """
    # 参数（应该配置化）
    RED_HARD = -1.8
    RED_CONDITION = -1.2
    GREEN_CONDITION = 0.3
    VOL_THRESHOLD = 1.2

    if market_chg <= RED_HARD:
        return {
            "gate": "RED",
            "new_entries": False,
            "reason": "hard_drop",
            "unit_R_multiplier": 0.0
        }
    elif market_chg <= RED_CONDITION and market_vol_ratio >= VOL_THRESHOLD:
        return {
            "gate": "RED",
            "new_entries": False,
            "reason": "drop_with_volume",
            "unit_R_multiplier": 0.0
        }
    elif market_chg >= GREEN_CONDITION and market_vol_ratio >= 0.9:
        return {
            "gate": "GREEN",
            "new_entries": True,
            "reason": "normal",
            "unit_R_multiplier": 1.0
        }
    else:
        return {
            "gate": "YELLOW",
            "new_entries": False,
            "reason": "neutral",
            "unit_R_multiplier": 0.7
        }


def calculate_sector_gate(
    sector_chg: float,
    market_chg: float,
    sector_vol_ratio: float
) -> Dict[str, Any]:
    """
    计算板块闸门

    Args:
        sector_chg: 板块竞价涨跌幅
        market_chg: 市场竞价涨跌幅
        sector_vol_ratio: 板块竞价量相对历史

    Returns:
        gate: RED/YELLOW/GREEN
    """
    rs = sector_chg - market_chg  # 相对强度

    # RED: 相对市场跌0.3%或板块跌0.8%且放量
    if rs <= -0.3 or (sector_chg <= -0.8 and sector_vol_ratio >= 1.2):
        return {
            "gate": "RED",
            "entry_mode": "none",
            "reason": "weak"
        }
    # GREEN: 相对市场强0.3%且板块不跌且放量
    elif rs >= 0.3 and sector_chg >= 0 and sector_vol_ratio >= 1.0:
        return {
            "gate": "GREEN",
            "entry_mode": "full",
            "reason": "strong"
        }
    else:
        return {
            "gate": "YELLOW",
            "entry_mode": "pullback_only",
            "reason": "neutral"
        }


def calculate_stock_gate(
    stock_chg: float,
    sector_chg: float,
    stock_vol_ratio: float,
    R: float = 0.05
) -> Dict[str, Any]:
    """
    计算个股闸门

    Args:
        stock_chg: 个股竞价涨跌幅
        sector_chg: 板块竞价涨跌幅
        stock_vol_ratio: 个股竞价量相对历史
        R: 风险单位 (默认5%)

    Returns:
        gate: RED/YELLOW/GREEN
    """
    rs = stock_chg - sector_chg  # 相对板块强度

    # RED: 相对板块跌0.5%或低开放量
    if rs <= -0.5 or (stock_chg < -2 and stock_vol_ratio >= 1.5):
        return {
            "gate": "RED",
            "action": "forbidden",
            "reason": "weak"
        }

    # YELLOW: 高开幅度过大导致赔率被吃光
    gap_over_R = stock_chg / (R * 100)  # 高开幅度相对R
    if gap_over_R > 1.5:  # 高开超过1.5R
        return {
            "gate": "YELLOW",
            "action": "reduced",
            "reason": "gap_too_large",
            "gap_over_R": round(gap_over_R, 2)
        }

    # GREEN: 其余
    return {
        "gate": "GREEN",
        "action": "allowed",
        "reason": "normal"
    }


def generate_auction_gate(
    trade_date: str = None,
    watchlist: List[str] = None,
    sector_codes: List[str] = None
) -> AuctionGateSignal:
    """
    生成集合竞价闸门

    Args:
        trade_date: 交易日期
        watchlist: 关注股票列表
        sector_codes: 关注的板块列表

    Returns:
        AuctionGateSignal
    """
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")

    run_id = f"auction_{trade_date}_{datetime.now().strftime('%H%M%S')}"
    qmt = get_qmt_client()

    # === 1. 市场闸门 ===
    # 需要从数据源获取市场竞价数据
    # 这里用上证指数快照估算
    market_data = get_auction_data("000001.SH")
    market_chg = 0.0  # 简化：需要从竞价接口获取
    market_vol_ratio = 1.0  # 简化

    market_gate = calculate_market_gate(market_chg, market_vol_ratio)
    market_gate.update({
        "symbol": "000001.SH",
        "chg_estimate": market_chg,
        "vol_ratio_estimate": market_vol_ratio
    })

    # === 2. 板块闸门 ===
    sector_gates = []
    if sector_codes:
        for sector in sector_codes:
            # 简化：需要板块竞价数据
            sector_chg = 0.0
            sector_vol_ratio = 1.0

            gate = calculate_sector_gate(sector_chg, market_chg, sector_vol_ratio)
            gate["sector_code"] = sector
            sector_gates.append(gate)

    # === 3. 个股闸门 ===
    stock_gates = []
    if watchlist:
        for stock in watchlist:
            # 简化：需要个股竞价数据
            stock_chg = 0.0
            stock_vol_ratio = 1.0

            # 获取所属板块
            sector_chg = 0.0  # 简化

            gate = calculate_stock_gate(stock_chg, sector_chg, stock_vol_ratio)
            gate["stock_code"] = stock
            stock_gates.append(gate)

    # === 4. 权限覆盖 ===
    market_gate_status = market_gate.get("gate", "YELLOW")
    permission_overrides = {
        "new_entries": market_gate.get("new_entries", False),
        "add_positions": market_gate_status == "GREEN",
        "reduce_positions": True,
        "unit_R_multiplier": market_gate.get("unit_R_multiplier", 1.0)
    }

    return AuctionGateSignal(
        run_id=run_id,
        trade_date=trade_date,
        timestamp=datetime.now().isoformat(),
        market_gate=market_gate,
        sector_gates=sector_gates,
        stock_gates=stock_gates,
        permission_overrides=permission_overrides
    )


def auction_gate_to_json(signal: AuctionGateSignal) -> str:
    """转换为 JSON"""
    return json.dumps(asdict(signal), ensure_ascii=False, indent=2)


def save_auction_gate(signal: AuctionGateSignal, path: str = None) -> str:
    """保存到文件"""
    if path is None:
        path = f"/Users/willbot/projects/00_Alapha_B/output/auction_gate_{signal.trade_date}.json"

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(auction_gate_to_json(signal))
    return path


if __name__ == "__main__":
    # 测试
    signal = generate_auction_gate(
        watchlist=["600536.SH", "600745.SH"],
        sector_codes=["TGNAI PC"]
    )
    print(auction_gate_to_json(signal))
