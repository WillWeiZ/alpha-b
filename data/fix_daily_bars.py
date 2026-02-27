#!/usr/bin/env python3
"""修复 daily_bars - 修复日期"""
import requests
from datetime import datetime, timedelta

QDB_URL = "http://localhost:9019"
QMT_URL = "http://192.168.31.147:8080"

def execute(query):
    resp = requests.get(f"{QDB_URL}/exec", params={"query": query}, timeout=60)
    if resp.status_code != 200:
        print(f"Error: {resp.text}")
        return None
    result = resp.json()
    if "error" in result:
        print(f"Error: {result['error']}")
        return None
    return result

# 1. 删除 daily_bars 中的指数
print("=== 1. 删除指数 ===")
indices = ['000001.SH', '399001.SZ', '399006.SZ', '000300.SH', '000016.SH', '000905.SH', '000852.SH']
for idx in indices:
    execute(f"DELETE FROM daily_bars WHERE symbol = '{idx}'")
    print(f"删除 {idx}")

# 2. 检查当前日期
print("\n=== 2. 当前数据 ===")
result = execute("SELECT min(ts), max(ts) FROM daily_bars")
print(f"日期范围: {result['dataset'][0]}")

# 测试一只股票
result = execute("SELECT ts, symbol, close FROM daily_bars WHERE symbol = '600000.SH' ORDER BY ts DESC LIMIT 3")
print("\n600000.SH 当前:")
for row in result['dataset']:
    print(f"  {row[0]} | {row[1]} | {row[2]}")

# 3. 从 QMT 获取一只股票测试日期格式
print("\n=== 3. 测试 QMT 数据 ===")
import requests
code = "600000.SH"
start = "20260225"
end = "20260226"

url = f"{QMT_URL}/v1/history/bars"
params = {"code": code, "freq": "1d", "start": start, "end": end}
resp = requests.get(url, params=params, timeout=30)
data = resp.json()
bars = data.get("bars", [])
print(f"获取 {code}: {len(bars)} 条")
for b in bars:
    print(f"  原始: {b['time']}")

    # 修复日期
    ts = b['time']
    if 'Z' in ts:
        dt = datetime.fromisoformat(ts.replace('Z', ''))
        dt = dt + timedelta(hours=8)  # UTC+8
        ts = dt.strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'
    print(f"  修复后: {ts}")

# 4. 检查 index_bars 验证日期
print("\n=== 4. index_bars 对比 ===")
result = execute("SELECT ts, symbol, close FROM index_bars WHERE symbol = '000001.SH' ORDER BY ts DESC LIMIT 3")
print("index_bars:")
for row in result['dataset']:
    print(f"  {row[0]} | {row[1]} | {row[2]}")
