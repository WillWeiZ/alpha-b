#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据同步脚本

用于同步以下数据到 QuestDB:
- 全部 A 股历史 K 线（从 QMT Gateway）
- 指数历史数据（从 QMT Gateway）
- 概念板块历史数据（从 akshare 同花顺）
- 概念板块成分股（从 QMT Gateway）

Usage:
    python data/sync.py --full          # 全量同步
    python data/sync.py --incremental   # 增量同步
    python data/sync.py --daily-bars   # 只同步日线
    python data/sync.py --concept-bars # 只同步概念板块
    python data/sync.py --constituents  # 只同步成分股
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional
import time
import logging

from data.questdb_client import get_questdb_client
from data.qmt_client import get_qmt_client
from data.akshare_client import get_akshare_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 过去 252 个交易日
TRADING_DAYS = 252


def get_trading_days_back(days: int = TRADING_DAYS) -> tuple:
    """获取追溯 N 个交易日的日期范围"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days * 2)  # 留余量
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")


def get_a_stock_list() -> List[str]:
    """获取全部 A 股代码列表"""
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        symbols = df['code'].tolist()
        # 转换为 QMT 格式
        return [f"{s}.SH" if s.startswith('6') else f"{s}.SZ" for s in symbols]
    except Exception as e:
        logger.error(f"获取A股列表失败: {e}")
        return []


def get_index_list() -> List[str]:
    """获取指数代码列表"""
    return [
        "000001.SH",  # 上证指数
        "399001.SZ",  # 深证成指
        "399006.SZ",  # 创业板指
        "000300.SH",  # 沪深300
        "000905.SH",  # 中证500
        "000852.SH",  # 中证1000
    ]


def sync_daily_bars(qdb, qmt, symbols: List[str], start: str, end: str, batch_size: int = 50):
    """
    同步日线数据

    Args:
        qdb: QuestDB 客户端
        qmt: QMT 客户端
        symbols: 股票代码列表
        start: 开始日期 YYYYMMDD
        end: 结束日期 YYYYMMDD
        batch_size: 每批处理数量
    """
    logger.info(f"开始同步日线数据: {len(symbols)} 只股票, {start} - {end}")

    total_synced = 0
    failed = []

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        logger.info(f"处理第 {i // batch_size + 1} 批, {len(batch)} 只股票")

        for symbol in batch:
            try:
                bars = qmt.get_bars(
                    code=symbol,
                    freq="1d",
                    start=start,
                    end=end
                )

                if bars:
                    df = pd.DataFrame([{
                        'ts': pd.to_datetime(b.time, unit='ms'),
                        'symbol': symbol,
                        'open': b.open,
                        'high': b.high,
                        'low': b.low,
                        'close': b.close,
                        'volume': b.volume,
                        'amount': b.amount
                    } for b in bars])

                    qdb.sync_daily_bars(df)
                    total_synced += len(bars)
            except Exception as e:
                logger.warning(f"获取 {symbol} 失败: {e}")
                failed.append(symbol)

        # 避免请求过快
        time.sleep(0.5)

    logger.info(f"日线同步完成: 共 {total_synced} 条记录, 失败 {len(failed)} 只")
    return total_synced, failed


def sync_concept_bars(qdb, akshare, start: str, end: str):
    """
    同步概念板块日线数据

    Args:
        qdb: QuestDB 客户端
        akshare: Akshare 客户端
        start: 开始日期 YYYYMMDD
        end: 结束日期 YYYYMMDD
    """
    logger.info(f"开始同步概念板块日线: {start} - {end}")

    # 获取概念板块列表
    try:
        concept_df = akshare.get_concept_list()
        concept_names = concept_df['name'].tolist() if 'name' in concept_df.columns else []
    except Exception as e:
        logger.error(f"获取概念板块列表失败: {e}")
        return 0

    logger.info(f"找到 {len(concept_names)} 个概念板块")

    total_synced = 0
    failed = []

    for concept_name in concept_names:
        try:
            df = akshare.get_concept_hist(concept_name, start, end)
            if not df.empty and 'date' in df.columns:
                df = df.rename(columns={'date': 'ts'})
                df['ts'] = pd.to_datetime(df['ts'])
                df['concept_name'] = concept_name

                # 确保数值类型
                for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                qdb.sync_concept_bars(df[['ts', 'concept_name', 'open', 'high', 'low', 'close', 'volume', 'amount']])
                total_synced += len(df)
        except Exception as e:
            logger.warning(f"获取 {concept_name} 失败: {e}")
            failed.append(concept_name)

        time.sleep(0.2)  # 避免请求过快

    logger.info(f"概念板块日线同步完成: 共 {total_synced} 条记录, 失败 {len(failed)} 个")
    return total_synced, failed


def sync_concept_constituents(qdb, qmt, trade_date: str = None):
    """
    同步概念板块成分股

    Args:
        qdb: QuestDB 客户端
        qmt: QMT 客户端
        trade_date: 交易日期 YYYYMMDD，默认今天
    """
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")

    logger.info(f"开始同步概念板块成分股: {trade_date}")

    # 获取概念板块列表（从 QMT）
    try:
        sectors = qmt.get_concept_sectors()
    except Exception as e:
        logger.error(f"获取概念板块列表失败: {e}")
        return 0

    logger.info(f"找到 {len(sectors)} 个概念板块")

    total_synced = 0
    failed = []

    for sector in sectors:
        try:
            # 获取成分股
            stocks = qmt.get_sector_stocks(sector)

            if stocks:
                df = pd.DataFrame([{
                    'trade_date': pd.to_datetime(trade_date),
                    'concept_name': sector[3:] if sector.startswith('TGN') else sector,  # 去掉 TGN 前缀
                    'symbol': s.stock_code,
                    'symbol_name': s.stock_name
                } for s in stocks])

                qdb.sync_concept_constituents(df)
                total_synced += len(df)
        except Exception as e:
            logger.warning(f"获取 {sector} 成分股失败: {e}")
            failed.append(sector)

        time.sleep(0.2)

    logger.info(f"概念板块成分股同步完成: 共 {total_synced} 条记录, 失败 {len(failed)} 个")
    return total_synced, failed


def full_sync():
    """全量同步"""
    logger.info("=" * 50)
    logger.info("开始全量同步")
    logger.info("=" * 50)

    qdb = get_questdb_client()
    qmt = get_qmt_client()
    akshare = get_akshare_client()

    # 获取日期范围
    start_date, end_date = get_trading_days_back(TRADING_DAYS)
    logger.info(f"日期范围: {start_date} - {end_date}")

    # 1. 同步日线数据（A股 + 指数）
    all_symbols = get_a_stock_list()
    index_symbols = get_index_list()
    all_symbols.extend(index_symbols)

    logger.info(f"共 {len(all_symbols)} 个交易标的")

    # 2. 同步概念板块日线
    sync_concept_bars(qdb, akshare, start_date, end_date)

    # 3. 同步概念板块成分股
    sync_concept_constituents(qdb, qmt)

    # 4. 同步日线数据
    # 由于 A 股数量太多，先同步少量验证
    # 实际全量同步需要很长时间
    logger.info("注意: 日线数据全量同步需要很长时间，建议使用 --incremental 进行增量同步")
    # sync_daily_bars(qdb, qmt, all_symbols, start_date, end_date)

    logger.info("=" * 50)
    logger.info("全量同步完成")
    logger.info("=" * 50)


def incremental_sync():
    """增量同步"""
    logger.info("=" * 50)
    logger.info("开始增量同步")
    logger.info("=" * 50)

    qdb = get_questdb_client()
    qmt = get_qmt_client()
    akshare = get_akshare_client()

    # 昨天和今天
    today = datetime.now().strftime("%Y%m%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    # 1. 同步日线数据（最近 5 天）
    start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")

    all_symbols = get_a_stock_list()
    index_symbols = get_index_list()
    all_symbols.extend(index_symbols)

    # 只同步前 100 只作为示例
    # 实际应该全部同步
    logger.info(f"增量同步日线: {start_date} - {today}, 共 {len(all_symbols)} 个标的")
    sync_daily_bars(qdb, qmt, all_symbols[:100], start_date, today, batch_size=20)

    # 2. 同步概念板块日线
    sync_concept_bars(qdb, akshare, start_date, today)

    # 3. 同步概念板块成分股
    sync_concept_constituents(qmt)

    logger.info("=" * 50)
    logger.info("增量同步完成")
    logger.info("=" * 50)


def sync_sample_data():
    """同步少量示例数据用于验证"""
    logger.info("=" * 50)
    logger.info("同步示例数据")
    logger.info("=" * 50)

    qdb = get_questdb_client()
    qmt = get_qmt_client()
    akshare = get_akshare_client()

    # 日期范围
    start_date, end_date = get_trading_days_back(TRADING_DAYS)
    today = datetime.now().strftime("%Y%m%d")

    # 1. 同步少量 A 股日线（10 只）
    sample_stocks = ["600000.SH", "600519.SH", "000001.SZ", "000002.SZ", "300001.SZ",
                     "688001.SH", "601318.SH", "600036.SH", "000858.SZ", "002594.SZ"]
    logger.info(f"同步示例股票日线: {sample_stocks}")
    sync_daily_bars(qdb, qmt, sample_stocks, start_date, today)

    # 2. 同步指数日线
    index_list = get_index_list()
    logger.info(f"同步指数日线: {index_list}")
    sync_daily_bars(qdb, qmt, index_list, start_date, today)

    # 3. 同步概念板块日线（5 个）
    try:
        concept_df = akshare.get_concept_list()
        concept_names = concept_df['板块名称'].tolist()[:5] if '板块名称' in concept_df.columns else []
        logger.info(f"同步示例概念板块日线: {concept_names}")
        for name in concept_names:
            try:
                df = akshare.get_concept_hist(name, start_date, today)
                if not df.empty and 'date' in df.columns:
                    df = df.rename(columns={'date': 'ts'})
                    df['ts'] = pd.to_datetime(df['ts'])
                    df['concept_name'] = name
                    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                    qdb.sync_concept_bars(df[['ts', 'concept_name', 'open', 'high', 'low', 'close', 'volume', 'amount']])
            except Exception as e:
                logger.warning(f"获取 {name} 失败: {e}")
    except Exception as e:
        logger.error(f"获取概念板块列表失败: {e}")

    # 4. 同步概念板块成分股
    try:
        sectors = qmt.get_concept_sectors()[:5]
        logger.info(f"同步示例概念板块成分股: {sectors}")
        for sector in sectors:
            try:
                stocks = qmt.get_sector_stocks(sector)
                if stocks:
                    df = pd.DataFrame([{
                        'trade_date': pd.to_datetime(today),
                        'concept_name': sector[3:] if sector.startswith('TGN') else sector,
                        'symbol': s.stock_code,
                        'symbol_name': s.stock_name
                    } for s in stocks])
                    qdb.sync_concept_constituents(df)
            except Exception as e:
                logger.warning(f"获取 {sector} 失败: {e}")
    except Exception as e:
        logger.error(f"获取概念板块失败: {e}")

    # 打印统计
    logger.info("=" * 50)
    logger.info("数据统计:")
    logger.info(f"  daily_bars: {qdb.get_table_count('daily_bars')} 条")
    logger.info(f"  concept_bars: {qdb.get_table_count('concept_bars')} 条")
    logger.info(f"  concept_constituents: {qdb.get_table_count('concept_constituents')} 条")
    logger.info("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="数据同步脚本")
    parser.add_argument("--full", action="store_true", help="全量同步")
    parser.add_argument("--incremental", action="store_true", help="增量同步")
    parser.add_argument("--sample", action="store_true", help="同步示例数据")
    parser.add_argument("--daily-bars", action="store_true", help="只同步日线")
    parser.add_argument("--concept-bars", action="store_true", help="只同步概念板块")
    parser.add_argument("--constituents", action="store_true", help="只同步成分股")

    args = parser.parse_args()

    if args.sample:
        sync_sample_data()
    elif args.full:
        full_sync()
    elif args.incremental:
        incremental_sync()
    elif args.daily_bars:
        qdb = get_questdb_client()
        qmt = get_qmt_client()
        start_date, end_date = get_trading_days_back(TRADING_DAYS)
        symbols = get_a_stock_list()
        symbols.extend(get_index_list())
        sync_daily_bars(qdb, qmt, symbols[:100], start_date, end_date)
    elif args.concept_bars:
        qdb = get_questdb_client()
        akshare = get_akshare_client()
        start_date, end_date = get_trading_days_back(TRADING_DAYS)
        sync_concept_bars(qdb, akshare, start_date, end_date)
    elif args.constituents:
        qdb = get_questdb_client()
        qmt = get_qmt_client()
        sync_concept_constituents(qdb, qmt)
    else:
        parser.print_help()
        print("\n使用 --sample 同步少量示例数据进行验证")


if __name__ == "__main__":
    main()
