#!/usr/bin/env python3
"""简单同步 - 不删除表"""
import requests
from datetime import datetime, timedelta

QDB_URL = "http://localhost:9019"
QMT_URL = "http://192.168.31.147:8080"
QMT_API_KEY = "iloveyou"

def execute(query):
    try:
        resp = requests.get(f"{QDB_URL}/exec", params={"query": query}, timeout=120)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None

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

# 确保表存在
print("确保表存在...")
execute("""
CREATE TABLE IF NOT EXISTS daily_bars (
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
for i, code in enumerate(symbols):
    bars = get_bars(code, start_date, end_date)
    if bars:
        values = []
        for b in bars:
            ts = timestamp_to_ts(b['time'])
            values.append(f"('{ts}', '{code}', {b['open']}, {b['high']}, {b['low']}, {b['close']}, {b['volume']}, {b['amount']})")

        # 批量写入
        for j in range(0, len(values), 100):
            sub = values[j:j+100]
            query = f"INSERT INTO daily_bars (ts, symbol, open, high, low, close, volume, amount) VALUES {','.join(sub)}"
            execute(query)

    total += len(bars)
    if (i + 1) % 50 == 0:
        print(f"进度: {i+1}/{len(symbols)} (总计: {total})")

print(f"完成: {total} 条")

# 验证
result = execute("SELECT count(*) FROM daily_bars")
print(f"总记录: {result['dataset'][0][0] if result else 0}")
