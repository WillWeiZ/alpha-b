#!/usr/bin/env python3
"""重新同步指数数据 - 使用正确的日期"""
import akshare as ak
import pandas as pd
import requests
from datetime import datetime, timedelta

QDB_URL = "http://localhost:9019"

def execute(query):
    resp = requests.get(f"{QDB_URL}/exec", params={"query": query}, timeout=30)
    if resp.status_code != 200:
        print(f"Error: {resp.text}")
        return None
    result = resp.json()
    if "error" in result:
        print(f"Error: {result['error']}")
        return None
    return result

# 清空 index_bars
print("=== 清空 index_bars ===")
execute("TRUNCATE TABLE index_bars")

# 指数代码映射
INDEX_MAP = {
    "000001": "000001.SH",   # 上证指数
    "399001": "399001.SZ",   # 深证成指
    "399006": "399006.SZ",   # 创业板指
    "000300": "000300.SH",   # 沪深300
    "000016": "000016.SH",   # 上证50
    "000905": "000905.SH",   # 中证500
    "000852": "000852.SH",   # 中证1000
}

# 需要获取的指数
indices_to_fetch = ["000001", "399001", "399006", "000300", "000016", "000905", "000852"]

# 时间范围 - 过去260天
end_date = datetime.now()
start_date = end_date - timedelta(days=300)
start_str = start_date.strftime("%Y%m%d")

print(f"获取时间范围: {start_str} - {end_date.strftime('%Y%m%d')}")

for ak_code in indices_to_fetch:
    db_code = INDEX_MAP.get(ak_code)
    print(f"\n=== 获取 {ak_code} -> {db_code} ===")

    try:
        if ak_code == "000001":
            df = ak.stock_zh_index_daily(symbol="sh000001")
        elif ak_code == "399001":
            df = ak.stock_zh_index_daily(symbol="sz399001")
        elif ak_code == "399006":
            df = ak.stock_zh_index_daily(symbol="sz399006")
        elif ak_code == "000300":
            df = ak.stock_zh_index_daily(symbol="sh000300")
        elif ak_code == "000016":
            df = ak.stock_zh_index_daily(symbol="sh000016")
        elif ak_code == "000905":
            df = ak.stock_zh_index_daily(symbol="sh000905")
        elif ak_code == "000852":
            df = ak.stock_zh_index_daily(symbol="sh000852")
    except Exception as e:
        print(f"Error: {e}")
        continue

    print(f"获取到 {len(df)} 条")

    # 过滤日期范围
    df['date'] = pd.to_datetime(df['date'])
    df = df[df['date'] >= start_date]
    df = df.sort_values('date')
    print(f"过滤后 {len(df)} 条")

    if len(df) == 0:
        continue

    # 写入 QuestDB - 使用中国日期 (不含时区信息)
    values = []
    for _, row in df.iterrows():
        # 使用日期字符串，不带时区
        # QuestDB 会把它当作 UTC，但显示时是中国日期
        # 例如: 2026-02-26T00:00:00.000000Z 代表中国日期 2026-02-26
        date_str = row['date'].strftime('%Y-%m-%d')
        ts = f"{date_str}T00:00:00.000000Z"
        volume = row.get('volume', 0) or 0
        amount = row.get('amount', 0) or 0
        values.append(f"('{ts}', '{db_code}', {row['open']}, {row['high']}, {row['low']}, {row['close']}, {volume}, {amount})")

    # 分批写入
    batch_size = 100
    for i in range(0, len(values), batch_size):
        batch = values[i:i+batch_size]
        query = f"INSERT INTO index_bars (ts, symbol, open, high, low, close, volume, amount) VALUES {','.join(batch)}"
        execute(query)

    print(f"写入完成! 最新: {df['date'].max()}")

# 验证
print("\n=== 最终结果 ===")
result = execute("SELECT symbol, count(*) FROM index_bars GROUP BY symbol ORDER BY symbol")
for row in result['dataset']:
    print(f"  {row[0]}: {row[1]} 条")

print("\n=== 检查日期 ===")
result = execute("SELECT ts, symbol, close FROM index_bars WHERE symbol = '000001.SH' ORDER BY ts DESC LIMIT 5")
if result and result.get('dataset'):
    for row in result['dataset']:
        print(f"{row[0]} | {row[1]} | {row[2]}")
