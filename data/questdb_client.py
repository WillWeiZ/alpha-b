# QuestDB 客户端

import pandas as pd
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from questdb.ingress import Sender, IngressError

from .config import get_settings


class QuestDBClient:
    """QuestDB 客户端"""

    def __init__(self, host: str = None, port: int = None, user: str = None, password: str = None):
        settings = get_settings()
        self.host = host or settings.questdb_host
        self.port = port or settings.questdb_port
        self.user = user or settings.questdb_user
        self.password = password or settings.questdb_password
        self._conn_str = f"http::req_fail_on_error=true;"

    def execute(self, sql: str) -> pd.DataFrame:
        """执行 SQL 查询"""
        import requests
        url = f"http://{self.host}:{self.port}/exec"
        resp = requests.get(url, params={"query": sql}, auth=(self.user, self.password))
        if resp.status_code != 200:
            raise Exception(f"QuestDB error: {resp.text}")

        # QuestDB 返回 JSON 格式
        try:
            data = resp.json()
            if 'error' in data:
                raise Exception(f"QuestDB error: {data.get('error')}")

            columns = [col['name'] for col in data.get('columns', [])]
            dataset = data.get('dataset', [])
            return pd.DataFrame(dataset, columns=columns)
        except Exception:
            # 如果不是 JSON，尝试 CSV 解析
            lines = resp.text.strip().split("\n")
            if len(lines) < 2:
                return pd.DataFrame()
            columns = lines[0].split(",")
            data = []
            for line in lines[1:]:
                if line.strip():
                    data.append(line.split(","))
            return pd.DataFrame(data, columns=columns)

    def insert_dataframe(self, df: pd.DataFrame, table: str):
        """批量写入 DataFrame"""
        # 确保 DataFrame 不为空
        if df.empty:
            return

        # 使用 /exec 端点执行 INSERT 语句
        for _, row in df.iterrows():
            values = []
            for col in df.columns:
                val = row[col]
                if pd.isna(val):
                    values.append('NULL')
                elif isinstance(val, (int, float)):
                    values.append(str(val))
                elif isinstance(val, str):
                    values.append(f"'{val}'")
                elif isinstance(val, pd.Timestamp):
                    # 转换为 ISO 格式字符串
                    ts_str = val.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
                    values.append(f"'{ts_str}'")
                elif hasattr(val, 'isoformat'):
                    values.append(f"'{val.isoformat()}'")
                else:
                    values.append(f"'{val}'")

            sql = f"INSERT INTO {table} ({','.join(df.columns)}) VALUES ({','.join(values)})"
            try:
                self.execute(sql)
            except Exception as e:
                # 忽略重复插入错误
                if 'duplicate' not in str(e).lower():
                    raise

    def create_tables(self):
        """创建新的表结构"""
        # 个股日线表
        self.execute("""
        CREATE TABLE IF NOT EXISTS daily_bars (
            ts TIMESTAMP,
            symbol STRING,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            amount DOUBLE
        ) TIMESTAMP(ts) PARTITION BY YEAR DEDUP UPSERT KEYS (ts, symbol);
        """)

        # 概念板块日线表
        self.execute("""
        CREATE TABLE IF NOT EXISTS concept_bars (
            ts TIMESTAMP,
            concept_name STRING,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            amount DOUBLE
        ) TIMESTAMP(ts) PARTITION BY YEAR DEDUP UPSERT KEYS (ts, concept_name);
        """)

        # 概念板块成分股表
        self.execute("""
        CREATE TABLE IF NOT EXISTS concept_constituents (
            ts TIMESTAMP,
            trade_date DATE,
            concept_name STRING,
            symbol STRING,
            symbol_name STRING
        ) TIMESTAMP(ts) PARTITION BY DAY DEDUP UPSERT KEYS (ts, trade_date, concept_name, symbol);
        """)

        # 指数日线表
        self.execute("""
        CREATE TABLE IF NOT EXISTS index_bars (
            ts TIMESTAMP,
            symbol STRING,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            amount DOUBLE
        ) TIMESTAMP(ts) PARTITION BY YEAR DEDUP UPSERT KEYS (ts, symbol);
        """)

    def create_table_if_not_exists(self):
        """创建旧的表结构（兼容旧版本）"""
        # 日线表
        self.execute("""
        CREATE TABLE IF NOT EXISTS bars_1d (
            ts TIMESTAMP,
            symbol STRING,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            amount DOUBLE,
            turnover DOUBLE
        ) TIMESTAMP(ts) PARTITION BY YEAR;
        """)

        # 分钟线表
        for freq in ["1m", "5m"]:
            self.execute(f"""
            CREATE TABLE IF NOT EXISTS bars_{freq} (
                ts TIMESTAMP,
                symbol STRING,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                amount DOUBLE
            ) TIMESTAMP(ts) PARTITION BY DAY;
            """)

        # 市场广度表
        self.execute("""
        CREATE TABLE IF NOT EXISTS market_breadth_1d (
            ts TIMESTAMP,
            up_count INT,
            down_count INT,
            limit_up_count INT,
            limit_down_count INT,
            total_volume DOUBLE,
            total_amount DOUBLE
        ) TIMESTAMP(ts) PARTITION BY YEAR;
        """)

        # 板块日线表
        self.execute("""
        CREATE TABLE IF NOT EXISTS sector_bars_1d (
            ts TIMESTAMP,
            sector_id STRING,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            amount DOUBLE
        ) TIMESTAMP(ts) PARTITION BY YEAR;
        """)

        # 集合竞价表
        self.execute("""
        CREATE TABLE IF NOT EXISTS auction_snap (
            ts TIMESTAMP,
            level STRING,
            id STRING,
            auction_chg_pct DOUBLE,
            auction_vol DOUBLE,
            auction_amount DOUBLE
        ) TIMESTAMP(ts) PARTITION BY YEAR;
        """)

        # 板块成分股映射表
        self.execute("""
        CREATE TABLE IF NOT EXISTS sector_membership (
            trade_date DATE,
            sector_id STRING,
            symbol STRING,
            PRIMARY KEY (trade_date, sector_id, symbol)
        );
        """)

    def sync_daily_bars(self, df: pd.DataFrame):
        """同步个股日线数据"""
        if df.empty:
            return
        # 确保列顺序
        cols = ['ts', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'amount']
        df = df[cols].copy()
        self.insert_dataframe(df, 'daily_bars')

    def sync_concept_bars(self, df: pd.DataFrame):
        """同步概念板块日线数据"""
        if df.empty:
            return
        cols = ['ts', 'concept_name', 'open', 'high', 'low', 'close', 'volume', 'amount']
        df = df[cols].copy()
        self.insert_dataframe(df, 'concept_bars')

    def sync_concept_constituents(self, df: pd.DataFrame):
        """同步概念板块成分股数据"""
        if df.empty:
            return
        # 添加 ts 列
        if 'ts' not in df.columns:
            df['ts'] = pd.to_datetime(df['trade_date'])
        cols = ['ts', 'trade_date', 'concept_name', 'symbol', 'symbol_name']
        df = df[cols].copy()
        self.insert_dataframe(df, 'concept_constituents')

    def sync_index_bars(self, df: pd.DataFrame):
        """同步指数日线数据"""
        if df.empty:
            return
        cols = ['ts', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'amount']
        df = df[cols].copy()
        self.insert_dataframe(df, 'index_bars')

    def query_index_bars(self, symbol: str, start: str = None, end: str = None, count: int = None):
        """查询指数日线"""
        sql = f"SELECT * FROM index_bars WHERE symbol = '{symbol}'"
        if start:
            sql += f" AND ts >= '{start}'"
        if end:
            sql += f" AND ts <= '{end}'"
        if count:
            sql += f" LIMIT {count}"
        return self.execute(sql)

    def get_latest_date(self, table: str, ts_col: str = 'ts') -> Optional[datetime]:
        """获取表中最新日期"""
        sql = f"SELECT max({ts_col}) as max_date FROM {table}"
        try:
            df = self.execute(sql)
            if not df.empty and 'max_date' in df.columns:
                val = df['max_date'].iloc[0]
                if val:
                    return pd.to_datetime(val)
        except Exception:
            pass
        return None

    def get_table_count(self, table: str) -> int:
        """获取表中的记录数"""
        sql = f"SELECT count(*) FROM {table}"
        try:
            df = self.execute(sql)
            if not df.empty:
                # QuestDB returns column name as 'count()'
                col = 'count()' if 'count()' in df.columns else df.columns[0]
                return int(df[col].iloc[0])
        except Exception:
            pass
        return 0

    def query_bars(self, symbol: str, start: str, end: str, freq: str = "1d") -> pd.DataFrame:
        """查询 K 线数据"""
        table = f"bars_{freq}"
        sql = f"""
        SELECT ts, symbol, open, high, low, close, volume, amount
        FROM {table}
        WHERE symbol = '{symbol}'
        AND ts >= '{start}'
        AND ts <= '{end}'
        ORDER BY ts ASC
        """
        return self.execute(sql)

    def query_daily_bars(self, symbol: str = None, start: str = None, end: str = None, limit: int = None) -> pd.DataFrame:
        """查询个股日线数据"""
        conditions = []
        if symbol:
            conditions.append(f"symbol = '{symbol}'")
        if start:
            conditions.append(f"ts >= '{start}'")
        if end:
            conditions.append(f"ts <= '{end}'")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
        SELECT ts, symbol, open, high, low, close, volume, amount
        FROM daily_bars
        WHERE {where_clause}
        ORDER BY ts ASC
        """
        if limit:
            sql += f" LIMIT {limit}"
        return self.execute(sql)

    def query_concept_bars(self, concept_name: str = None, start: str = None, end: str = None, limit: int = None) -> pd.DataFrame:
        """查询概念板块日线数据"""
        conditions = []
        if concept_name:
            conditions.append(f"concept_name = '{concept_name}'")
        if start:
            conditions.append(f"ts >= '{start}'")
        if end:
            conditions.append(f"ts <= '{end}'")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
        SELECT ts, concept_name, open, high, low, close, volume, amount
        FROM concept_bars
        WHERE {where_clause}
        ORDER BY ts ASC
        """
        if limit:
            sql += f" LIMIT {limit}"
        return self.execute(sql)

    def query_concept_constituents(self, trade_date: str = None, concept_name: str = None) -> pd.DataFrame:
        """查询概念板块成分股数据"""
        conditions = []
        if trade_date:
            conditions.append(f"trade_date = '{trade_date}'")
        if concept_name:
            conditions.append(f"concept_name = '{concept_name}'")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
        SELECT trade_date, concept_name, symbol, symbol_name
        FROM concept_constituents
        WHERE {where_clause}
        """
        return self.execute(sql)

    def query_market_breadth(self, start: str, end: str) -> pd.DataFrame:
        """查询市场广度"""
        sql = f"""
        SELECT ts, up_count, down_count, limit_up_count, limit_down_count
        FROM market_breadth_1d
        WHERE ts >= '{start}' AND ts <= '{end}'
        ORDER BY ts ASC
        """
        return self.execute(sql)

    def get_concept_list(self) -> List[str]:
        """
        获取概念板块列表

        数据来源: QuestDB concept_constituents 表
        """
        sql = "SELECT DISTINCT concept_name FROM concept_constituents ORDER BY concept_name"
        result = self.execute(sql)
        if result is not None and not result.empty:
            return result['concept_name'].tolist()
        return []

    def get_concept_stocks(self, concept_name: str) -> List[Dict[str, str]]:
        """
        获取指定概念的成分股列表

        Args:
            concept_name: 概念名称

        Returns:
            [{"stock_code": "600000.SH", "stock_name": "浦发银行"}, ...]

        数据来源: QuestDB concept_constituents 表
        """
        sql = f"""
        SELECT DISTINCT symbol, symbol_name
        FROM concept_constituents
        WHERE concept_name = '{concept_name}'
        """
        df = self.execute(sql)
        if df is not None and not df.empty:
            return [
                {"stock_code": row['symbol'], "stock_name": row['symbol_name']}
                for _, row in df.iterrows()
            ]
        return []


# 全局客户端实例
_qdb_client: Optional[QuestDBClient] = None


def get_questdb_client() -> QuestDBClient:
    global _qdb_client
    if _qdb_client is None:
        _qdb_client = QuestDBClient()
    return _qdb_client
