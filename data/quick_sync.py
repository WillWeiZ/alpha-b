#!/usr/bin/env python3
"""快速同步 daily_bars"""
import requests
from datetime import datetime, timedelta
import time

QDB_URL = "http://localhost:9019"
QMT_URL = "http://192.168.31.147:8080"
QMT_API_KEY = "iloveyou"

def execute(query):
    resp = requests.get(f"{QDB_URL}/exec", params={"query": query}, timeout=60)
    return resp.json() if resp.status_code == 200 else None

def get_bars(code, start, end):
    url = f"{QMT_URL}/v1/history/bars"
    params = {"code": code, "freq": "1d", "start": start, "end": end}
    headers = {"X-API-Key": QMT_API_KEY}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        data = resp.json()
        return data.get("data", {}).get("bars", []) if data.get("code") == 0 else []
    except:
        return []

def timestamp_to_ts(ts_ms):
    dt = datetime.utcfromtimestamp(ts_ms / 1000)
    dt = dt + timedelta(hours=8)
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

# 获取股票列表
print("获取股票列表...")
result = execute("SELECT DISTINCT symbol FROM concept_constituents")
symbols = [r[0] for r in result['dataset']] if result else []
print(f"股票数量: {len(symbols)}")

# 时间范围
end_date = "20260226"
start_date = (datetime.now() - timedelta(days=320)).strftime("%Y%m%d")
print(f"范围: {start_date} - {end_date}")

# 同步
total = 0
batch_size = 30

for i in range(0, len(symbols), batch_size):
    batch = symbols[i:i+batch_size]
    batch_num = i // batch_size + 1
    total_batches = (len(symbols) + batch_size - 1) // batch_size

    all_bars = []
    for code in batch:
        bars = get_bars(code, start_date, end_date)
        for b in bars:
            ts = timestamp_to_ts(b['time'])
            all_bars.append((ts, code, b['open'], b['high'], b['low'], b['close'], b['volume'], b['amount']))

    if all_bars:
        values = []
        for b in all_bars:
            values.append(f"('{b[0]}', '{b[1]}', {b[2]}, {b[3]}, {b[4]}, {b[5]}, {b[6]}, {b[7]})")

        for j in range(0, len(values), 100):
            sub = values[j:j+100]
            query = f"INSERT INTO daily_bars (ts, symbol, open, high, low, close, volume, amount) VALUES {','.join(sub)}"
            execute(query)

    total += len(all_bars)
    print(f"Batch {batch_num}/{total_batches}: {len(all_bars)} 条 (总计: {total})")

print(f"\n完成: {total} 条")

# 验证
result = execute("SELECT min(ts), max(ts), count(*) FROM daily_bars")
print(f"日期范围: {result['dataset'][0]}")
