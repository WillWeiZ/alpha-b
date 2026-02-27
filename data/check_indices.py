#!/usr/bin/env python3
"""检查 daily_bars 中的指数数据"""
import requests

QDB_URL = "http://localhost:9019"

def execute(query):
    resp = requests.get(f"{QDB_URL}/exec", params={"query": query}, timeout=30)
    if resp.status_code != 200:
        print(f"Error: {resp.text}")
        return None
    result = resp.json()
    if "error" in result:
        return None
    return result

# 检查 daily_bars 中的所有指数
indices = ['000001.SH', '399001.SZ', '399006.SZ', '000300.SH', '000016.SH', '000905.SH', '000852.SH']

print("=== daily_bars 中的指数 ===")
for idx in indices:
    result = execute(f"SELECT count(*) FROM daily_bars WHERE symbol = '{idx}'")
    count = result['dataset'][0][0] if result else 0
    print(f"{idx}: {count} 条")

print("\n=== index_bars 中的指数 ===")
result = execute("SELECT symbol, count(*) FROM index_bars GROUP BY symbol")
for row in result['dataset']:
    print(f"{row[0]}: {row[1]} 条")
