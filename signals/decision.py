# 信号引擎 - Decision (盘中决策)
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
class DecisionSignal:
    """盘中决策信号"""
    run_id: str
    trade_date: str
    timestamp: str
    market_status: Dict[str, Any]  # 当前市场状态
    positions: List[Dict[str, Any]]  # 持仓决策
    watchlist: List[Dict[str, Any]]  # 关注列表决策
    actions: List[Dict[str, Any]]  # 动作列表


def get_current_prices(codes: List[str]) -> Dict[str, Dict]:
    """
    获取实时价格

    注意: 此函数使用 QMT Gateway 获取实时快照数据
    数据来源: QMT Gateway get_snapshot() - 实时数据
    """
    qmt = get_qmt_client()
    try:
        snapshot = qmt.get_snapshot(codes)
        return snapshot
    except Exception as e:
        print(f"获取快照失败: {e}")
        return {}


def calculate_position_decision(
    stock_code: str,
    entry_price: float,
    current_price: float,
    stop_price: float,
    R: float,
    market_state: str
) -> Dict[str, Any]:
    """
    计算持仓决策

    Args:
        stock_code: 股票代码
        entry_price: 入场价格
        current_price: 当前价格
        stop_price: 止损价格
        R: 1R 风险
        market_state: 市场状态

    Returns:
        decision: HOLD/REDUCE/SELL
    """
    # 当前盈亏
    pnl_pct = (current_price - entry_price) / entry_price
    pnL_r = pnl_pct / R if R > 0 else 0  # 多少R

    # 止损判断
    if current_price <= stop_price:
        return {
            "action": "SELL",
            "reason": "stop_loss",
            "pnl_pct": round(pnl_pct * 100, 2),
            "pnl_r": round(pnL_r, 2)
        }

    # 止盈判断 (3R以上可以分批卖)
    if pnL_r >= 3:
        return {
            "action": "REDUCE",
            "reason": "take_profit_3R",
            "pnl_pct": round(pnl_pct * 100, 2),
            "pnl_r": round(pnL_r, 2)
        }

    # 市场极端时保护利润
    if market_state == "沸":
        if pnL_r >= 2:
            return {
                "action": "REDUCE",
                "reason": "market_hot_protect",
                "pnl_pct": round(pnl_pct * 100, 2),
                "pnl_r": round(pnL_r, 2)
            }

    # 持有
    return {
        "action": "HOLD",
        "reason": "normal",
        "pnl_pct": round(pnl_pct * 100, 2),
        "pnl_r": round(pnL_r, 2)
    }


def calculate_watchlist_decision(
    stock_code: str,
    current_price: float,
    entry_trigger: str,
    gate_status: str,
    market_state: str
) -> Dict[str, Any]:
    """
    计算关注列表决策

    Args:
        stock_code: 股票代码
        current_price: 当前价格
        entry_trigger: 入场触发条件
        gate_status: 闸门状态
        market_state: 市场状态

    Returns:
        decision: BUY/CANCEL_PLAN/HOLD
    """
    # 闸门禁止新开仓
    if gate_status == "RED":
        return {
            "action": "CANCEL_PLAN",
            "reason": "gate_red",
            "stock_code": stock_code
        }

    # 市场不允许
    if market_state in ["冻", "寒"]:
        return {
            "action": "CANCEL_PLAN",
            "reason": "market_cold",
            "stock_code": stock_code
        }

    # 触发买入
    if entry_trigger == "回踩EMA20":
        # 需要判断是否回踩到位
        # 简化：假设价格接近EMA20就买
        return {
            "action": "BUY",
            "reason": "pullback_trigger",
            "stock_code": stock_code
        }
    elif entry_trigger == "突破20日高点":
        # 需要判断是否突破
        return {
            "action": "BUY",
            "reason": "breakout_trigger",
            "stock_code": stock_code
        }

    return {
        "action": "HOLD",
        "reason": "waiting",
        "stock_code": stock_code
    }


def generate_decision(
    trade_date: str = None,
    positions: List[Dict] = None,
    watchlist: List[Dict] = None,
    plan_data: Dict = None
) -> DecisionSignal:
    """
    生成盘中决策

    Args:
        trade_date: 交易日期
        positions: 当前持仓列表 [{"stock_code": "xxx", "entry_price": 10.0, "stop_price": 9.5, "r_price": 0.5}]
        watchlist: 关注列表 [{"stock_code": "xxx", "entry_trigger": "回踩EMA20"}]
        plan_data: 当日计划数据

    Returns:
        DecisionSignal
    """
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")

    run_id = f"decision_{trade_date}_{datetime.now().strftime('%H%M%S')}"
    qmt = get_qmt_client()

    # === 1. 市场状态 ===
    # 简化：从plan获取或实时计算
    market_state = plan_data.get("market_state_7", "平") if plan_data else "平"
    gate_status = "GREEN"  # 简化：应该从auction_gate获取

    market_status = {
        "market_state": market_state,
        "gate_status": gate_status,
        "timestamp": datetime.now().isoformat()
    }

    # === 2. 持仓决策 ===
    position_decisions = []
    if positions:
        # 获取实时价格
        codes = [p["stock_code"] for p in positions]
        prices = get_current_prices(codes)

        for pos in positions:
            stock = pos["stock_code"]
            current = prices.get(stock, {}).get("last_price", pos.get("entry_price", 0))

            decision = calculate_position_decision(
                stock_code=stock,
                entry_price=pos["entry_price"],
                current_price=current,
                stop_price=pos["stop_price"],
                R=pos.get("r_price", 0.05),
                market_state=market_state
            )
            decision["stock_code"] = stock
            decision["current_price"] = current
            position_decisions.append(decision)

    # === 3. 关注列表决策 ===
    watchlist_decisions = []
    if watchlist:
        codes = [w["stock_code"] for w in watchlist]
        prices = get_current_prices(codes)

        for w in watchlist:
            stock = w["stock_code"]
            current = prices.get(stock, {}).get("last_price", 0)

            decision = calculate_watchlist_decision(
                stock_code=stock,
                current_price=current,
                entry_trigger=w.get("entry_trigger", "回踩EMA20"),
                gate_status=gate_status,
                market_state=market_state
            )
            decision["current_price"] = current
            watchlist_decisions.append(decision)

    # === 4. 汇总动作 ===
    actions = []

    # 持仓动作
    for dec in position_decisions:
        if dec["action"] in ["SELL", "REDUCE"]:
            actions.append({
                "type": dec["action"],
                "stock_code": dec["stock_code"],
                "reason": dec["reason"],
                "priority": 1  # 高优先级
            })

    # 关注列表动作
    for dec in watchlist_decisions:
        if dec["action"] == "BUY":
            actions.append({
                "type": "BUY",
                "stock_code": dec["stock_code"],
                "reason": dec["reason"],
                "priority": 2
            })
        elif dec["action"] == "CANCEL_PLAN":
            actions.append({
                "type": "CANCEL_PLAN",
                "stock_code": dec["stock_code"],
                "reason": dec["reason"],
                "priority": 3
            })

    # 按优先级排序
    actions.sort(key=lambda x: x["priority"])

    return DecisionSignal(
        run_id=run_id,
        trade_date=trade_date,
        timestamp=datetime.now().isoformat(),
        market_status=market_status,
        positions=position_decisions,
        watchlist=watchlist_decisions,
        actions=actions
    )


def decision_to_json(signal: DecisionSignal) -> str:
    """转换为 JSON"""
    return json.dumps(asdict(signal), ensure_ascii=False, indent=2)


def save_decision(signal: DecisionSignal, path: str = None) -> str:
    """保存到文件"""
    if path is None:
        path = f"/Users/willbot/projects/00_Alapha_B/output/decision_{signal.trade_date}_{signal.timestamp.replace(':', '')}.json"

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(decision_to_json(signal))
    return path


if __name__ == "__main__":
    # 测试
    positions = [
        {"stock_code": "600536.SH", "entry_price": 45.0, "stop_price": 42.0, "r_price": 3.0}
    ]
    watchlist = [
        {"stock_code": "600745.SH", "entry_trigger": "回踩EMA20"}
    ]

    signal = generate_decision(positions=positions, watchlist=watchlist)
    print(decision_to_json(signal))
