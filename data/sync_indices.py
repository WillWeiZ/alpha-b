#!/usr/bin/env python3
"""从 QMT Gateway 同步指数数据"""
import sys
sys.path.insert(0, '/Users/willbot/projects/00_Alapha_B')

import requests
from datetime import datetime, timedelta

QDB_URL = "http://localhost:9019"
QMT_URL = "http://192.168.31.147:8080"

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

def get_bars_from_qmt(code, start, end):
    """从 QMT 获取 bar 数据"""
    url = f"{QMT_URL}/v1/history/bars"
    params = {"code": code, "freq": "1d", "start": start, "end": end}
    try:
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        return data.get("bars", [])
    except Exception as e:
        print(f"Error fetching {code}: {e}")
        return []

# 指数列表
indices = [
    ("000001.SH", "上证指数"),
    ("399001.SZ", "深证成指"),
    ("399006.SZ", "创业板指"),
    ("000300.SH", "沪深300"),
    ("000016.SH", "上证50"),
    ("000905.SH", "中证500"),
    ("000852.SH", "中证1000"),
]

# 时间范围：过去1年
end_date = datetime.now().strftime("%Y%m%d")
start_date = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")

print(f"同步时间范围: {start_date} - {end_date}")

for code, name in indices:
    print(f"\n=== 同步 {code} ({name}) ===")

    # 检查现有数量
    result = execute(f"SELECT count(*) FROM index_bars WHERE symbol = '{code}'")
    existing = result['dataset'][0][0] if result else 0
    print(f"现有: {existing} 条")

    # 从 QMT 获取
    bars = get_bars_from_qmt(code, start_date, end_date)
    print(f"获取: {len(bars)} 条")

    if bars:
        # 写入 QuestDB
        values = []
        for b in bars:
            ts = b['time'].replace('Z', '') if 'Z' in b['time'] else b['time']
            values.append(f"('{ts}', '{code}', {b['open']}, {b['high']}, {b['low']}, {b['close']}, {b['volume']}, {b['amount']})")

        # 分批写入
        batch_size = 100
        for i in range(0, len(values), batch_size):
            batch = values[i:i+batch_size]
            query = f"INSERT INTO index_bars (ts, symbol, open, high, low, close, volume, amount) VALUES {','.join(batch)}"
            execute(query)

        print(f"写入完成!")

# 验证
print("\n=== 最终结果 ===")
result = execute("SELECT symbol, count(*) FROM index_bars GROUP BY symbol ORDER BY symbol")
for row in result['dataset']:
    print(f"  {row[0]}: {row[1]} 条")
