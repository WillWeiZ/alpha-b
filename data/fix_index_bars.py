#!/usr/bin/env python3
"""修复 index_bars 表 - 使用 INSERT 语句"""
import requests
import pandas as pd
import time

QDB_URL = "http://localhost:9019"

def execute(query, retry=3):
    for i in range(retry):
        try:
            resp = requests.get(f"{QDB_URL}/exec", params={"query": query}, timeout=30)
            if resp.status_code != 200:
                print(f"Error: {resp.text}")
                time.sleep(1)
                continue
            result = resp.json()
            if "error" in result:
                print(f"Error: {result['error']}")
                time.sleep(1)
                continue
            return result
        except Exception as e:
            print(f"Retry {i+1}: {e}")
            time.sleep(2)
    return None

# 查询需要的指数从 daily_bars
print("=== 1. 从 daily_bars 读取指数数据 ===")
indices_needed = ['399006.SZ', '000852.SH', '000016.SH', '000300.SH', '000001.SH', '399001.SZ']
df_all = pd.DataFrame()

for idx in indices_needed:
    result = execute(f"SELECT * FROM daily_bars WHERE symbol = '{idx}'")
    if result and result['dataset']:
        df_new = pd.DataFrame(result['dataset'], columns=['ts', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'amount'])
        df_all = pd.concat([df_all, df_new], ignore_index=True)
        print(f"读取 {idx}: {len(df_new)} 条")

# 去重
df_all = df_all.drop_duplicates(subset=['ts', 'symbol'])
print(f"\n总计: {len(df_all)} 条")

# 重建表
print("\n=== 2. 重建 index_bars ===")
execute("DROP TABLE IF EXISTS index_bars")

execute("""
CREATE TABLE IF NOT EXISTS index_bars (
    ts TIMESTAMP,
    symbol STRING,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    amount DOUBLE
) TIMESTAMP(ts) PARTITION BY YEAR DEDUP UPSERT KEYS (ts, symbol)
""")

# 格式化时间戳
def format_ts(ts):
    ts = str(ts)
    if 'Z' in ts:
        ts = ts.replace('Z', '')
    return ts

# 批量写入 - 每 100 条一批
print("=== 3. 批量写入数据 ===")
batch_size = 100

for symbol in df_all['symbol'].unique():
    df_symbol = df_all[df_all['symbol'] == symbol].sort_values('ts')
    total = len(df_symbol)
    batches = (total + batch_size - 1) // batch_size

    for i in range(0, total, batch_size):
        batch = df_symbol.iloc[i:i+batch_size]
        values = []
        for _, row in batch.iterrows():
            ts = format_ts(row['ts'])
            values.append(f"('{ts}', '{row['symbol']}', {row['open']}, {row['high']}, {row['low']}, {row['close']}, {row['volume']}, {row['amount']})")

        query = f"INSERT INTO index_bars (ts, symbol, open, high, low, close, volume, amount) VALUES {','.join(values)}"
        result = execute(query)

        batch_num = i // batch_size + 1
        if result:
            print(f"写入 {symbol}: {batch_num}/{batches} 批")
        else:
            print(f"Error writing {symbol} batch {batch_num}")
        time.sleep(0.1)  # 避免太快

print("\n=== 4. 验证结果 ===")
result = execute("SELECT symbol, count(*) FROM index_bars GROUP BY symbol ORDER BY symbol")
for row in result['dataset']:
    print(f"  {row[0]}: {row[1]} 条")
