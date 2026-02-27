#!/usr/bin/env python3
"""
数据同步脚本 - 每日收盘后更新
用法:
    python data/daily_sync.py          # 手动运行一次
    # 设置定时任务 (每日17:00执行):
    # crontab -e
    # 0 17 * * 1-5 /usr/bin/python3 /Users/willbot/projects/00_Alapha_B/data/daily_sync.py
"""
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/daily_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import akshare as ak
import pandas as pd

# ============ 配置 ============
QDB_URL = "http://localhost:9019"
QMT_URL = "http://192.168.31.147:8080"
QMT_API_KEY = "iloveyou"

# 交易日历文件
TRADING_CALENDAR_FILE = "/Users/willbot/projects/00_Alapha_B/data/trading_calendar.csv"

# ============ 工具函数 ============

def execute(query):
    """执行 QuestDB 查询"""
    try:
        resp = requests.get(f"{QDB_URL}/exec", params={"query": query}, timeout=120)
        if resp.status_code != 200:
            logger.error(f"Query failed: {resp.text}")
            return None
        result = resp.json()
        if "error" in result:
            logger.error(f"Query error: {result['error']}")
            return None
        return result
    except Exception as e:
        logger.error(f"Execute error: {e}")
        return None

def get_trading_calendar(force_update=False):
    """
    获取A股交易日历
    如果本地有保存且未过期则使用本地，否则从akshare获取
    """
    calendar_file = Path(TRADING_CALENDAR_FILE)

    # 检查本地文件是否存在且未过期（7天内）
    if not force_update and calendar_file.exists():
        mtime = datetime.fromtimestamp(calendar_file.stat().st_mtime)
        if (datetime.now() - mtime).days < 7:
            df = pd.read_csv(calendar_file)
            logger.info(f"使用本地交易日历: {len(df)} 天")
            return set(df['date'].astype(str).tolist())

    # 从akshare获取
    logger.info("从akshare获取交易日历...")
    try:
        # 尝试获取未来一年的交易日
        df = ak.tool_trade_date_hist_sina()

        # 过滤：只保留交易日期（is_trading_day=True）
        if 'is_trading_day' in df.columns:
            df = df[df['is_trading_day'] == 1]

        # 转换为日期字符串
        if 'date' in df.columns:
            dates = df['date'].astype(str).tolist()
        else:
            dates = df.iloc[:, 0].astype(str).tolist()

        # 保存到本地
        calendar_df = pd.DataFrame({'date': dates})
        calendar_df.to_csv(calendar_file, index=False)
        logger.info(f"交易日历已保存: {len(dates)} 天")

        return set(dates)
    except Exception as e:
        logger.error(f"获取交易日历失败: {e}")
        # 尝试备用方法
        return get_trading_calendar_backup()

def get_trading_calendar_backup():
    """备用方法：使用简单的历史交易日推算"""
    logger.info("使用备用交易日历...")
    # 简单逻辑：周六日不交易，节假日手动排除
    dates = []
    for i in range(365):
        d = datetime.now() - timedelta(days=i)
        if d.weekday() < 5:  # 周一到周五
            dates.append(d.strftime('%Y-%m-%d'))

    # 保存
    calendar_df = pd.DataFrame({'date': dates})
    calendar_df.to_csv(Path(TRADING_CALENDAR_FILE), index=False)
    return set(dates)

def is_trading_day(date=None):
    """检查指定日期是否是交易日"""
    if date is None:
        date = datetime.now()
    date_str = date.strftime('%Y-%m-%d')

    calendar = get_trading_calendar()
    return date_str in calendar

def get_latest_trading_day():
    """获取最新的交易日（今天或上一个交易日）"""
    today = datetime.now()

    # 如果今天是交易日，返回今天
    if is_trading_day(today):
        return today.strftime('%Y%m%d')

    # 否则找上一个交易日
    for i in range(1, 10):
        d = today - timedelta(days=i)
        if is_trading_day(d):
            return d.strftime('%Y%m%d')

    return (today - timedelta(days=1)).strftime('%Y%m%d')

# ============ 数据同步函数 ============

def timestamp_to_ts(ts_ms):
    """时间戳转 ISO 格式，加8小时"""
    dt = datetime.utcfromtimestamp(ts_ms / 1000)
    dt = dt + timedelta(hours=8)
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

def get_bars_from_qmt(code, start, end):
    """从 QMT 获取 bars"""
    url = f"{QMT_URL}/v1/history/bars"
    params = {"code": code, "freq": "1d", "start": start, "end": end}
    headers = {"X-API-Key": QMT_API_KEY}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        data = resp.json()
        if data.get("code") == 0:
            return data.get("data", {}).get("bars", [])
        return []
    except Exception as e:
        logger.error(f"获取 {code} 失败: {e}")
        return []

def sync_daily_bars():
    """同步个股日线数据"""
    logger.info("=== 同步个股日线 ===")

    # 获取需要更新的股票列表（排除北交所）
    result = execute("SELECT DISTINCT symbol FROM concept_constituents WHERE symbol NOT LIKE '%BJ'")
    symbols = [r[0] for r in result['dataset']] if result else []
    logger.info(f"股票数量: {len(symbols)}")

    # 获取最新日期
    result = execute("SELECT max(ts) FROM daily_bars")
    if result and result.get('dataset'):
        max_ts = result['dataset'][0][0]
        if max_ts:
            max_date = str(max_ts)[:10]
            start_date = (datetime.strptime(max_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
        else:
            start_date = (datetime.now() - timedelta(days=300)).strftime("%Y%m%d")
    else:
        start_date = (datetime.now() - timedelta(days=300)).strftime("%Y%m%d")

    end_date = get_latest_trading_day()
    logger.info(f"范围: {start_date} - {end_date}")

    if start_date > end_date:
        logger.info("无需更新")
        return

    total = 0
    for i, code in enumerate(symbols):
        bars = get_bars_from_qmt(code, start_date, end_date)

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
        if (i + 1) % 100 == 0:
            logger.info(f"进度: {i+1}/{len(symbols)} (新增: {total})")

    logger.info(f"个股日线同步完成: {total} 条")

def sync_index_bars():
    """同步指数日线数据"""
    logger.info("=== 同步指数日线 ===")

    # 指数列表
    indices = {
        "sh000001": "000001.SH",  # 上证指数
        "sz399001": "399001.SZ",  # 深证成指
        "sz399006": "399006.SZ",  # 创业板指
        "sh000300": "000300.SH",  # 沪深300
        "sh000016": "000016.SH",  # 上证50
        "sh000905": "000905.SH",  # 中证500
        "sh000852": "000852.SH",  # 中证1000
    }

    # 获取最新日期
    result = execute("SELECT max(ts) FROM index_bars")
    if result and result.get('dataset'):
        max_ts = result['dataset'][0][0]
        if max_ts:
            max_date = str(max_ts)[:10]
            start_date = (datetime.strptime(max_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
        else:
            start_date = (datetime.now() - timedelta(days=300)).strftime("%Y%m%d")
    else:
        start_date = (datetime.now() - timedelta(days=300)).strftime("%Y%m%d")

    end_date = get_latest_trading_day()
    logger.info(f"范围: {start_date} - {end_date}")

    if start_date > end_date:
        logger.info("指数无需更新")
        return

    for ak_code, db_code in indices.items():
        try:
            df = ak.stock_zh_index_daily(symbol=ak_code)

            # 过滤日期范围
            df['date'] = pd.to_datetime(df['date'])
            df = df[df['date'] >= start_date]
            df = df[df['date'] <= end_date]

            if len(df) == 0:
                continue

            # 写入
            values = []
            for _, row in df.iterrows():
                date_str = row['date'].strftime('%Y-%m-%d')
                ts = f"{date_str}T00:00:00.000000Z"
                volume = row.get('volume', 0) or 0
                values.append(f"('{ts}', '{db_code}', {row['open']}, {row['high']}, {row['low']}, {row['close']}, {volume}, 0)")

            for j in range(0, len(values), 100):
                sub = values[j:j+100]
                query = f"INSERT INTO index_bars (ts, symbol, open, high, low, close, volume, amount) VALUES {','.join(sub)}"
                execute(query)

            logger.info(f"{db_code}: {len(df)} 条")
        except Exception as e:
            logger.error(f"{db_code} 失败: {e}")

    logger.info("指数日线同步完成")

def sync_concept_bars():
    """同步概念板块日线数据"""
    logger.info("=== 同步概念板块日线 ===")

    # 获取需要同步的概念板块
    result = execute("SELECT DISTINCT concept_name FROM concept_constituents")
    concepts = [r[0] for r in result['dataset']] if result else []
    logger.info(f"概念板块: {len(concepts)} 个")

    # 获取最新日期
    result = execute("SELECT max(ts) FROM concept_bars")
    if result and result.get('dataset'):
        max_ts = result['dataset'][0][0]
        if max_ts:
            max_date = str(max_ts)[:10]
            start_date = (datetime.strptime(max_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
        else:
            start_date = (datetime.now() - timedelta(days=300)).strftime("%Y%m%d")
    else:
        start_date = (datetime.now() - timedelta(days=300)).strftime("%Y%m%d")

    end_date = get_latest_trading_day()
    logger.info(f"范围: {start_date} - {end_date}")

    if start_date > end_date:
        logger.info("概念板块无需更新")
        return

    for concept in concepts:
        try:
            # 使用同花顺概念板块接口
            df = ak.stock_board_concept_index_ths(symbol=concept)

            if df is None or len(df) == 0:
                continue

            # 过滤日期
            if '日期' in df.columns:
                df['date'] = pd.to_datetime(df['日期'])
            elif 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            else:
                continue

            df = df[df['date'] >= start_date]
            df = df[df['date'] <= end_date]

            if len(df) == 0:
                continue

            # 写入
            values = []
            for _, row in df.iterrows():
                date_str = row['date'].strftime('%Y-%m-%d')
                ts = f"{date_str}T00:00:00.000000Z"
                volume = row.get('涨跌幅', 0) or row.get('成交量', 0) or 0
                values.append(f"('{ts}', '{concept}', {row.get('开盘', 0)}, {row.get('最高', 0)}, {row.get('最低', 0)}, {row.get('收盘', row.get('最新价', 0))}, {volume}, 0)")

            for j in range(0, len(values), 100):
                sub = values[j:j+100]
                query = f"INSERT INTO concept_bars (ts, concept_name, open, high, low, close, volume, amount) VALUES {','.join(sub)}"
                execute(query)

            logger.info(f"{concept}: {len(df)} 条")
        except Exception as e:
            logger.error(f"{concept} 失败: {e}")

    logger.info("概念板块日线同步完成")

def update_trading_calendar():
    """更新交易日历"""
    logger.info("=== 更新交易日历 ===")
    calendar = get_trading_calendar(force_update=True)
    logger.info(f"交易日历: {len(calendar)} 天")

# ============ 同步报告 ============

def generate_report():
    """生成同步报告"""
    logger.info("=" * 50)
    logger.info("【同步报告】")
    trading_day = get_latest_trading_day()
    logger.info(f"交易日期: {trading_day}")
    logger.info("")

    # 1. 个股报告
    logger.info("--- 个股 (daily_bars) ---")
    result = execute("SELECT min(ts), max(ts), count(DISTINCT symbol) FROM daily_bars")
    if result and result.get('dataset'):
        r = result['dataset'][0]
        logger.info(f"  股票数量: {r[2]}")
        logger.info(f"  日期范围: {str(r[0])[:10]} ~ {str(r[1])[:10]}")

    # 今日新增
    result = execute(f"SELECT count(*) FROM daily_bars WHERE ts >= '{trading_day}'")
    if result and result.get('dataset'):
        logger.info(f"  今日新增: {result['dataset'][0][0]} 条")

    # 2. 指数报告
    logger.info("")
    logger.info("--- 指数 (index_bars) ---")
    result = execute("SELECT symbol, max(ts), count(*) FROM index_bars GROUP BY symbol ORDER BY symbol")
    if result and result.get('dataset'):
        for r in result['dataset']:
            logger.info(f"  {r[0]}: {str(r[1])[:10]} ({r[2]}条)")

    # 3. 概念板块报告
    logger.info("")
    logger.info("--- 概念板块 (concept_bars) ---")

    # 预期板块数
    result = execute("SELECT count(DISTINCT concept_name) FROM concept_constituents")
    expected_concepts = result['dataset'][0][0] if result else 0
    logger.info(f"  预期板块数: {expected_concepts}")

    # 成功同步的板块
    result = execute("SELECT count(DISTINCT concept_name) FROM concept_bars")
    synced_concepts = result['dataset'][0][0] if result else 0
    logger.info(f"  已同步板块数: {synced_concepts}")

    # 各板块最新日期
    result = execute("SELECT concept_name, max(ts) as max_ts FROM concept_bars GROUP BY concept_name")
    if result and result.get('dataset'):
        by_date = {}
        for r in result['dataset']:
            ts = str(r[1])[:10]
            by_date.setdefault(ts, []).append(r[0])
        logger.info(f"  最新数据分布:")
        for ts, concepts in sorted(by_date.items(), reverse=True):
            logger.info(f"    {ts}: {len(concepts)}个")

    logger.info("=" * 50)

# ============ 主函数 ============

def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info(f"开始同步: {datetime.now()}")

    # 检查是否交易日
    if not is_trading_day():
        logger.info("今天不是交易日，跳过")
        # 但仍更新交易日历
        update_trading_calendar()
        return

    logger.info(f"今天是交易日: {get_latest_trading_day()}")

    # 更新交易日历
    update_trading_calendar()

    # 同步数据
    try:
        sync_daily_bars()
    except Exception as e:
        logger.error(f"个股同步失败: {e}")

    try:
        sync_index_bars()
    except Exception as e:
        logger.error(f"指数同步失败: {e}")

    try:
        sync_concept_bars()
    except Exception as e:
        logger.error(f"概念板块同步失败: {e}")

    # 生成同步报告
    generate_report()

if __name__ == "__main__":
    main()
