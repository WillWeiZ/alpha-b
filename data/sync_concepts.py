#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
同步指定的板块数据
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime
import time

from data.questdb_client import get_questdb_client
from data.qmt_client import get_qmt_client
from data.akshare_client import get_akshare_client

# 要同步的板块列表
CONCEPTS = [
    "共封装光学",
    "AI应用",
    "存储芯片",
    "多模态AI",
    "液冷服务器",
    "算力租赁",
    "AI手机",
    "人形机器人",
    "Sora概念",
    "AI PC",
    "PCB概念",
    "黄金概念",
    "稀土永磁",
    "金属铜",
    "军工信息化",
    "商业航天",
    "低空经济",
    "固态电池",
    "创新药",
    "鸿蒙概念",
    "星闪概念",
    "AI语料",
    "机器人概念",
    "煤炭概念",
    "磷化工",
    "氟化工概念",
    "钙钛矿电池",
    "无人驾驶",
    "智能座舱",
    "宠物经济",
    "DeepSeek概念",
    "AI智能体",
    "东数西算",
    "铜缆高速连接",
    "脑机接口",
    "数据要素",
    "光刻机",
    "工业母机",
    "华为盘古",
    "华为手机",
    "国产操作系统",
    "股权转让",
    "央企国企改革",
    "同花顺出海50",
    "IP经济",
    "减肥药",
]

def sync_concept_bars(qdb, akshare, concepts, start_date, end_date):
    """同步概念板块日线"""
    print(f"开始同步 {len(concepts)} 个概念板块日线...")

    synced = 0
    failed = []

    for i, concept in enumerate(concepts):
        print(f"[{i+1}/{len(concepts)}] {concept}...", end=" ")
        try:
            df = akshare.get_concept_hist(concept, start_date, end_date)
            if not df.empty and 'date' in df.columns:
                df = df.rename(columns={'date': 'ts'})
                df['ts'] = pd.to_datetime(df['ts'])
                df['concept_name'] = concept
                for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                qdb.sync_concept_bars(df[['ts', 'concept_name', 'open', 'high', 'low', 'close', 'volume', 'amount']])
                print(f"{len(df)} rows")
                synced += 1
            else:
                print("No data")
        except Exception as e:
            print(f"FAILED: {e}")
            failed.append(concept)

        time.sleep(0.3)

    print(f"\n概念板块日线同步完成: {synced} 成功, {len(failed)} 失败")
    return synced, failed


def sync_concept_constituents(qdb, qmt, concepts):
    """同步概念板块成分股"""
    print(f"\n开始同步 {len(concepts)} 个概念板块成分股...")

    synced = 0
    failed = []

    # 尝试从 QMT 获取
    try:
        qmt_sectors = qmt.get_concept_sectors()
        print(f"QMT 板块数: {len(qmt_sectors)}")
    except Exception as e:
        print(f"获取 QMT 板块失败: {e}")
        qmt_sectors = []

    # QMT 板块名映射
    qmt_map = {}
    for s in qmt_sectors:
        # TGN开头的去掉TGN
        name = s[3:] if s.startswith('TGN') else s
        qmt_map[name] = s

    today = datetime.now().strftime("%Y%m%d")

    for i, concept in enumerate(concepts):
        print(f"[{i+1}/{len(concepts)}] {concept}...", end=" ")
        try:
            # 尝试从 QMT 获取
            qmt_code = qmt_map.get(concept)
            if qmt_code:
                stocks = qmt.get_sector_stocks(qmt_code)
                if stocks:
                    df = pd.DataFrame([{
                        'ts': pd.to_datetime(today),
                        'trade_date': pd.to_datetime(today),
                        'concept_name': concept,
                        'symbol': s.stock_code,
                        'symbol_name': s.stock_name
                    } for s in stocks])
                    qdb.sync_concept_constituents(df)
                    print(f"{len(df)} stocks")
                    synced += len(df)
                    continue

            print("No data")
        except Exception as e:
            print(f"FAILED: {e}")
            failed.append(concept)

        time.sleep(0.2)

    print(f"\n概念板块成分股同步完成: {synced} 条")
    return synced, failed


def sync_stock_bars(qdb, qmt, symbols, start_date, end_date, batch_size=50):
    """同步个股日线"""
    print(f"\n开始同步 {len(symbols)} 只股票日线...")

    total_synced = 0
    failed = []

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size
        print(f"Batch {batch_num}/{total_batches} ({len(batch)} stocks)...")

        for symbol in batch:
            try:
                bars = qmt.get_bars(code=symbol, freq="1d", start=start_date, end=end_date)
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
                failed.append(symbol)

            time.sleep(0.1)

    print(f"\n个股日线同步完成: {total_synced} 条, {len(failed)} 失败")
    return total_synced, failed


def main():
    print("=" * 60)
    print("同步指定板块数据")
    print("=" * 60)

    qdb = get_questdb_client()
    qmt = get_qmt_client()
    akshare = get_akshare_client()

    start_date = "20250101"
    end_date = datetime.now().strftime("%Y%m%d")

    print(f"日期范围: {start_date} - {end_date}")

    # 1. 同步概念板块日线
    sync_concept_bars(qdb, akshare, CONCEPTS, start_date, end_date)

    # 2. 同步概念板块成分股
    sync_concept_constituents(qdb, qmt, CONCEPTS)

    # 3. 获取所有成分股代码
    print("\n获取所有成分股代码...")
    all_symbols = set()
    for concept in CONCEPTS:
        try:
            constituents = qdb.query_concept_constituents(concept_name=concept)
            if not constituents.empty:
                all_symbols.update(constituents['symbol'].tolist())
        except:
            pass

    print(f"共获取 {len(all_symbols)} 只股票")

    # 4. 同步个股日线
    if all_symbols:
        sync_stock_bars(qdb, qmt, list(all_symbols), start_date, end_date)

    # 5. 打印统计
    print("\n" + "=" * 60)
    print("数据统计:")
    print(f"  daily_bars: {qdb.get_table_count('daily_bars')} 条")
    print(f"  concept_bars: {qdb.get_table_count('concept_bars')} 条")
    print(f"  concept_constituents: {qdb.get_table_count('concept_constituents')} 条")
    print("=" * 60)


if __name__ == "__main__":
    main()
