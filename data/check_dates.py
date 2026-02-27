#!/usr/bin/env python3
"""检查 index_bars 数据"""
import requests

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

# 查看上证指数最近的数据
print("=== 上证指数最近数据 ===")
result = execute("SELECT ts, symbol, close FROM index_bars WHERE symbol = '000001.SH' ORDER BY ts DESC LIMIT 10")
if result and result.get('dataset'):
    for row in result['dataset']:
        print(f"{row[0]} | {row[1]} | {row[2]}")

print("\n=== 检查 daily_bars 个股最近数据 ===")
result = execute("SELECT ts, symbol, close FROM daily_bars WHERE symbol = '600000.SH' ORDER BY ts DESC LIMIT 10")
if result and result.get('dataset'):
    for row in result['dataset']:
        print(f"{row[0]} | {row[1]} | {row[2]}")

print("\n=== 检查每天有多少条记录 ===")
result = execute("SELECT substr(cast(ts as string), 1, 10) as date, count(*) FROM daily_bars WHERE symbol = '600000.SH' GROUP BY date ORDER BY date DESC LIMIT 5")
if result and result.get('dataset'):
    for row in result['dataset']:
        print(f"{row[0]}: {row[1]} 条")
