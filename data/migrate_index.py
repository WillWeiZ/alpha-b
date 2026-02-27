#!/usr/bin/env python3
"""迁移指数数据到 index_bars 并清理 daily_bars"""
import requests

QDB_URL = "http://localhost:9019"

def execute(query):
    resp = requests.get(f"{QDB_URL}/exec", params={"query": query})
    print(f"Query: {query}")
    if resp.status_code != 200:
        print(f"Error: {resp.text}")
        return None
    result = resp.json()
    if "error" in result:
        print(f"Error: {result['error']}")
        return None
    print(f"OK - {result.get('dml', result.get('ddl', result.get('count', 'done')))}")
    return result

# 创建新表排除指数
execute("""
CREATE TABLE IF NOT EXISTS daily_bars_new (
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

# 插入非指数数据
execute("""
INSERT INTO daily_bars_new
SELECT ts, symbol, open, high, low, close, volume, amount
FROM daily_bars
WHERE symbol != '000001.SZ'
AND symbol != '000001.SH'
AND symbol != '399001.SZ'
AND symbol != '000300.SH'
""")

# 检查新表
result = execute("SELECT count(*) FROM daily_bars_new")
if result:
    print(f"新表行数: {result['dataset'][0][0]}")

# 重命名表
execute("RENAME TABLE daily_bars TO daily_bars_old")
execute("RENAME TABLE daily_bars_new TO daily_bars")

# 检查
result = execute("SELECT count(*) FROM daily_bars")
if result:
    print(f"daily_bars 行数: {result['dataset'][0][0]}")

result = execute("SELECT count(*) FROM index_bars")
if result:
    print(f"index_bars 行数: {result['dataset'][0][0]}")
