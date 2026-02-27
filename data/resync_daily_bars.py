#!/usr/bin/env python3
"""重新同步 daily_bars - 使用正确的日期格式"""
import requests
from datetime import datetime, timedelta

QDB_URL = "http://localhost:9019"
QMT_URL = "http://192.168.31.147:8080"
QMT_API_KEY = "iloveyou"

def execute(query):
    resp = requests.get(f"{QDB_URL}/exec", params={"query": query}, timeout=60)
    if resp.status_code != 200:
        return None
    result = resp.json()
    if "error" in result:
        return None
    return result

def get_bars(code, start, end):
    """从 QMT 获取 bars"""
    url = f"{QMT_URL}/v1/history/bars"
    params = {"code": code, "freq": "1d", "start": start, "end": end}
    headers = {"X-API-Key": QMT_API_KEY}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        data = resp.json()
        if data.get("code") == 0:
            return data.get("data", {}).get("bars", [])
        return []
    except:
        return []

def timestamp_to_ts(ts_ms):
    """时间戳转 ISO 格式，加8小时使日期正确"""
    # QMT 返回 UTC 16:00 = 中国次日 00:00
    # 加8小时后变成 UTC 次日 00:00，这样 QuestDB 显示的日期就是正确的中国日期
    dt = datetime.utcfromtimestamp(ts_ms / 1000)
    dt = dt + timedelta(hours=8)
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

# 1. 从 concept_constituents 获取股票列表（排除北交所）
print("=== 1. 获取股票列表 ===")
result = execute("SELECT DISTINCT symbol FROM concept_constituents WHERE symbol NOT LIKE '%BJ'")
symbols = [r[0] for r in result['dataset']] if result else []
print(f"股票数量: {len(symbols)}")

# 2. 创建新表
print("\n=== 2. 创建新表 ===")
execute("DROP TABLE IF EXISTS daily_bars_new")

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

# 3. 重新同步
print("\n=== 3. 同步数据 ===")

end_date = "20260226"
start_date = (datetime.now() - timedelta(days=320)).strftime("%Y%m%d")
print(f"范围: {start_date} - {end_date}")

total = 0
batch_size = 50

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
            query = f"INSERT INTO daily_bars_new (ts, symbol, open, high, low, close, volume, amount) VALUES {','.join(sub)}"
            execute(query)

    total += len(all_bars)
    if batch_num % 5 == 0:
        print(f"Batch {batch_num}/{total_batches}: {len(all_bars)} 条 (总计: {total})")

print(f"\n同步完成: {total} 条")

# 4. 替换表
print("\n=== 4. 替换表 ===")
execute("DROP TABLE IF EXISTS daily_bars")
execute("RENAME TABLE daily_bars_new TO daily_bars")

# 5. 验证
print("\n=== 5. 验证 ===")
result = execute("SELECT min(ts), max(ts) FROM daily_bars")
print(f"日期范围: {result['dataset'][0]}")

result = execute("SELECT count(*) FROM daily_bars")
print(f"总记录: {result['dataset'][0][0]}")

result = execute("SELECT ts, symbol, close FROM daily_bars WHERE symbol = '600000.SH' ORDER BY ts DESC LIMIT 3")
print("\n600000.SH 最近:")
for row in result['dataset']:
    print(f"  {row[0]} | {row[1]} | {row[2]}")

print("\n完成!")
