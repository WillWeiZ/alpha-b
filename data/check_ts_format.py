#!/usr/bin/env python3
"""检查 akshare 写入的数据"""
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

# 检查所有唯一时间戳格式
print("=== 检查 index_bars 时间戳格式 ===")
result = execute("SELECT cast(ts as string) as ts_str, count(*) FROM index_bars GROUP BY ts_str LIMIT 10")
if result and result.get('dataset'):
    for row in result['dataset']:
        print(f"{row[0]}: {row[1]} 条")

print("\n=== 检查 daily_bars 时间戳格式 ===")
result = execute("SELECT cast(ts as string) as ts_str, count(*) FROM daily_bars GROUP BY ts_str LIMIT 10")
if result and result.get('dataset'):
    for row in result['dataset']:
        print(f"{row[0]}: {row[1]} 条")
