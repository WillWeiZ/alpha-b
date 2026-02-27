# 信号引擎 - Plan 生成 (T-1 盘后)
#
# 数据来源:
# - 大盘K线: QuestDB index_bars 表
# - 板块K线: QuestDB concept_bars 表
# - 成分股列表: QuestDB concept_constituents 表
# - 个股K线: QuestDB daily_bars 表

import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from features import (
    MarketHeatResult, calculate_market_heat,
    SectorHeatResult, calculate_sector_heat,
    StockHeatResult, calculate_stock_heat
)
from data import get_questdb_client


@dataclass
class PlanSignal:
    """Plan 信号"""
    run_id: str
    trade_date: str
    market_plan: Dict[str, Any]  # 市场计划
    sector_plans: List[Dict[str, Any]]  # 板块计划
    stock_plans: List[Dict[str, Any]]  # 个股计划
    risk_controls: Dict[str, Any]  # 风险控制
    forbidden_actions: List[str]  # 禁止行为


def generate_plan(
    trade_date: str = None,
    top_sectors: int = 5,
    top_stocks_per_sector: int = 3
) -> PlanSignal:
    """
    生成 T-1 计划

    Args:
        trade_date: 交易日期 YYYYMMDD
        top_sectors: 选几个热门板块
        top_stocks_per_sector: 每个板块选几只股

    Returns:
        PlanSignal
    """
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")

    run_id = f"plan_{trade_date}_{datetime.now().strftime('%H%M%S')}"
    qdb = get_questdb_client()

    # === 1. 大盘环境 (MarketHeat) ===
    indices = ['000001.SH', '000300.SH', '000852.SH']
    bars_dict = {}

    for idx in indices:
        import pandas as pd
        df = qdb.query_daily_bars(symbol=idx, limit=300)
        if not df.empty:
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['ts'] = pd.to_datetime(df['ts'])
            df = df.set_index('ts').sort_index()
            bars_dict[idx] = df

    market_heat = calculate_market_heat(bars_dict.get('000001.SH')) if bars_dict else None

    market_plan = {
        "market_heat_score": round(market_heat.market_heat, 1) if market_heat else 50,
        "market_state_7": market_heat.market_state_7 if market_heat else "平",
        "risk_mode": market_heat.risk_mode if market_heat else "CAUTIOUS",
        "trend_score": round(market_heat.trend_score, 1) if market_heat else 50,
        "breadth_score": round(market_heat.breadth_score, 1) if market_heat else 50,
    }

    # === 2. 板块选择 (SectorHeat) ===
    # 获取概念板块列表（从 QuestDB）
    # 数据来源: QuestDB concept_constituents 表
    all_sectors = qdb.get_concept_list()

    # 过滤：只保留有实际内容的板块（去掉纯年份的）
    concept_sectors = [s for s in all_sectors if not s[3:].startswith('20')]

    # 简化：只计算前5个板块
    sector_plans = []

    for sector in concept_sectors[:5]:
        try:
            sector_heat = calculate_sector_heat(sector)
            if sector_heat.is_candidate:
                sector_plans.append({
                    "sector_code": sector,
                    "sector_heat": round(sector_heat.sector_heat, 1),
                    "rs_score": round(sector_heat.rs_score, 1),
                    "diffusion_score": round(sector_heat.diffusion_score, 1),
                    "is_candidate": bool(sector_heat.is_candidate),
                })
        except Exception as e:
            continue

    # 按热度排序
    sector_plans.sort(key=lambda x: x['sector_heat'], reverse=True)
    sector_plans = sector_plans[:top_sectors]

    # === 3. 个股选择 (StockHeat) ===
    stock_plans = []

    for sector_plan in sector_plans:
        sector = sector_plan['sector_code']
        try:
            # 从 QuestDB 获取成分股列表
            # 数据来源: QuestDB concept_constituents 表
            stocks = qdb.get_concept_stocks(sector)
            # 过滤沪深A股
            a_stocks = [s for s in stocks if s.get('stock_code', '').endswith('.SH') or s.get('stock_code', '').endswith('.SZ')]

            for stock in a_stocks[:top_stocks_per_sector]:
                try:
                    stock_heat = calculate_stock_heat(stock['stock_code'], sector)
                    if stock_heat.stock_heat > 40:  # 热度阈值
                        stock_plans.append({
                            "stock_code": stock['stock_code'],
                            "stock_name": stock['stock_name'],
                            "sector_code": sector,
                            "stock_heat": round(stock_heat.stock_heat, 1),
                            "breakout_level": stock_heat.breakout_level,
                            "pullback_zone": stock_heat.pullback_zone,
                            "stop_price": round(stock_heat.stop_price, 2),
                            "r_price": round(stock_heat.r_price, 2),
                            "entry_trigger": "回踩EMA20" if stock_heat.pullback_zone == "EMA20附近" else "突破20日高点",
                        })
                except Exception as e:
                    continue
        except Exception as e:
            continue

    # 按热度排序
    stock_plans.sort(key=lambda x: x['stock_heat'], reverse=True)

    # === 4. 风险控制 ===
    risk_mode = market_heat.risk_mode if market_heat else "CAUTIOUS"

    risk_controls = {
        "max_positions": 5 if risk_mode == "AGGRESSIVE" else 3,
        "max_single_risk": 0.02,  # 单票最大2%风险
        "max_total_risk": 0.06,   # 总仓位最大6%风险
        "new_entry_allowed": risk_mode != "SAFE",
        "reduce_allowed": True,
    }

    # === 5. 禁止行为 ===
    forbidden_actions = []
    if risk_mode == "SAFE":
        forbidden_actions = ["new_entry", "add_position"]
    elif risk_mode == "CAUTIOUS":
        forbidden_actions = ["new_entry"]

    return PlanSignal(
        run_id=run_id,
        trade_date=trade_date,
        market_plan=market_plan,
        sector_plans=sector_plans,
        stock_plans=stock_plans,
        risk_controls=risk_controls,
        forbidden_actions=forbidden_actions
    )


def plan_to_json(plan: PlanSignal) -> str:
    """转换为 JSON 字符串"""
    return json.dumps(asdict(plan), ensure_ascii=False, indent=2)


def save_plan(plan: PlanSignal, path: str = None) -> str:
    """保存到文件"""
    if path is None:
        path = f"/Users/willbot/projects/00_Alapha_B/output/plan_{plan.trade_date}.json"

    os.makedirs(os.path.dirname(path), exist_ok=True)
    json_str = plan_to_json(plan)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(json_str)
    return path


if __name__ == "__main__":
    # 测试
    plan = generate_plan()
    print(plan_to_json(plan))
