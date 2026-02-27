#!/usr/bin/env python3
"""测试同步 - 只同步少量数据"""
import requests
from datetime import datetime, timedelta
import sys

QDB_URL = "http://localhost:9019"
QMT_URL = "http://192.168.31.147:8080"
QMT_API_KEY = "iloveyou"

def execute(query):
    print(f"Executing: {query[:50]}...", file=sys.stderr)
    resp = requests.get(f"{QDB_URL}/exec", params={"query": query}, timeout=60)
    if resp.status_code != 200:
        print(f"Error: {resp.text}", file=sys.stderr)
        return None
    result = resp.json()
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return None
    return result

# 1. 从 concept_constituents 获取前10只股票（排除北交所）
print("=== 1. 获取股票列表 ===")
result = execute("SELECT DISTINCT symbol FROM concept_constituents WHERE symbol NOT LIKE '%BJ' LIMIT 10")
symbols = [r[0] for r in result['dataset']] if result else []
print(f"股票: {symbols}")

# 2. 获取测试数据
print("\n=== 2. 测试获取数据 ===")
end_date = "20260226"
start_date = "20260224"

for code in symbols[:3]:
    url = f"{QMT_URL}/v1/history/bars"
    params = {"code": code, "freq": "1d", "start": start_date, "end": end_date}
    headers = {"X-API-Key": QMT_API_KEY}
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    data = resp.json()
    print(f"{code}: {data.get('message', data)}")
