#!/usr/bin/env python3
"""修复 daily_bars 时区问题 - 添加 8 小时"""
import requests
import json

# QuestDB API
QDB_URL = "http://localhost:9019"

def execute(query):
    resp = requests.get(f"{QDB_URL}/exec", params={"query": query})
    if resp.status_code != 200:
        print(f"Error: {resp.text}")
        return None
    result = resp.json()
    if "error" in result:
        print(f"Query Error: {result['error']}")
        return None
    return result

# 检查当前数据情况
print("=== 当前数据 ===")
result = execute("SELECT count(*) FROM daily_bars")
print(f"总行数: {result['dataset'][0][0]}")

# 获取日期范围
result = execute("SELECT min(ts), max(ts) FROM daily_bars")
print(f"日期范围: {result['dataset'][0]}")

# 检查日期格式 - 用 cast
print("\n=== 检查日期格式 ===")
result = execute("SELECT cast(ts as string) as ts_str FROM daily_bars LIMIT 3")
print(f"日期字符串: {result['dataset']}")

# 获取所有唯一日期 - 用 cast
print("\n=== 唯一日期 ===")
result = execute("""
SELECT distinct substr(cast(ts as string), 1, 10) as date_str
FROM daily_bars
order by date_str desc
limit 10
""")
print(f"唯一日期: {result['dataset']}")
