# QMT Gateway API 客户端

import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import time

from .config import get_settings


class QMTError(Exception):
    """QMT API 错误"""
    def __init__(self, code: int, message: str, trace_id: str = None):
        self.code = code
        self.message = message
        self.trace_id = trace_id
        super().__init__(f"[{code}] {message}")


@dataclass
class Bar:
    """K线数据"""
    time: int  # 毫秒时间戳
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


@dataclass
class SectorStock:
    """板块成分股"""
    stock_code: str
    stock_name: str


class QMTClient:
    """QMT Gateway 客户端"""

    def __init__(self, base_url: str = None, api_key: str = None, timeout: int = None):
        settings = get_settings()
        self.base_url = base_url or settings.qmt_base_url
        self.api_key = api_key or settings.qmt_api_key
        self.timeout = timeout or settings.qmt_timeout
        self._session = requests.Session()
        self._session.headers.update({"X-API-Key": self.api_key})

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """发送请求"""
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)
        resp = self._session.request(method, url, **kwargs)
        data = resp.json()
        if data.get("code") != 0:
            raise QMTError(
                data.get("code", -1),
                data.get("message", "Unknown error"),
                data.get("trace_id")
            )
        return data.get("data", {})

    def health(self) -> Dict[str, Any]:
        """健康检查"""
        return self._request("GET", "/v1/health")

    def get_balance(self) -> Dict[str, Any]:
        """查询账户余额"""
        return self._request("GET", "/v1/account/balance")

    def get_positions(self, stock_code: str = None) -> List[Dict[str, Any]]:
        """查询持仓"""
        params = {"stock_code": stock_code} if stock_code else {}
        data = self._request("GET", "/v1/account/positions", params=params)
        return data.get("positions", [])

    def get_orders(self, status: str = "ALL", order_id: int = None) -> List[Dict[str, Any]]:
        """查询委托"""
        params = {"status": status}
        if order_id:
            params["order_id"] = order_id
        data = self._request("GET", "/v1/orders", params=params)
        return data.get("orders", [])

    def place_order(
        self,
        stock_code: str,
        direction: str,
        volume: int,
        price: float = None,
        price_type: str = "FIX_PRICE",
        intent_id: str = None,
        strategy_name: str = ""
    ) -> Dict[str, Any]:
        """下单"""
        payload = {
            "stock_code": stock_code,
            "direction": direction,
            "volume": volume,
            "price_type": price_type,
        }
        if price is not None:
            payload["price"] = price
        if intent_id:
            payload["intent_id"] = intent_id
        if strategy_name:
            payload["strategy_name"] = strategy_name

        return self._request("POST", "/v1/orders", json=payload)

    def cancel_order(self, order_id: int) -> Dict[str, Any]:
        """撤单"""
        return self._request("POST", "/v1/orders/cancel", json={"order_id": order_id})

    def get_snapshot(self, codes: List[str]) -> Dict[str, Any]:
        """行情快照"""
        params = {"code": ",".join(codes)}
        return self._request("GET", "/v1/market/snapshot", params=params)

    def get_bars(
        self,
        code: str,
        freq: str = "1d",
        start: str = None,
        end: str = None,
        count: int = None
    ) -> List[Bar]:
        """
        获取历史K线

        Args:
            code: 股票代码，如 600000.SH
            freq: 周期 1m/5m/1d
            start: 开始日期 YYYYMMDD 或 YYYYMMDDHHmmss
            end: 结束日期
            count: 返回条数（需要配合start使用）
        """
        from datetime import datetime, timedelta

        params = {"code": code, "freq": freq}

        # API 必须提供 start，如果只给 count 则自动计算 start
        if start:
            params["start"] = start
        elif count:
            # 用当前日期向前推算
            if freq == "1d":
                delta = timedelta(days=count * 2)  # 留点余量
            else:
                delta = timedelta(days=count)
            start_date = (datetime.now() - delta).strftime("%Y%m%d")
            params["start"] = start_date
        else:
            # 默认取最近一年
            params["start"] = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")

        if end:
            params["end"] = end

        data = self._request("GET", "/v1/history/bars", params=params)
        bars = data.get("bars", [])

        # 如果指定了 count，截取最后 count 条
        if count and len(bars) > count:
            bars = bars[-count:]

        return [Bar(
            time=b["time"],
            open=b["open"],
            high=b["high"],
            low=b["low"],
            close=b["close"],
            volume=b["volume"],
            amount=b["amount"]
        ) for b in bars]

    def get_sectors(self) -> List[str]:
        """获取板块列表"""
        data = self._request("GET", "/v1/market/sectors")
        return data.get("sectors", [])

    def get_sector_stocks(self, sector: str) -> List[SectorStock]:
        """获取板块成分股"""
        params = {"sector": sector}
        data = self._request("GET", "/v1/market/sector-stocks", params=params)
        stocks = data.get("stocks", [])
        return [SectorStock(stock_code=s["stock_code"], stock_name=s["stock_name"]) for s in stocks]

    def get_concept_sectors(self) -> List[str]:
        """获取概念板块列表（ TGN 开头，过滤 sync ）"""
        all_sectors = self.get_sectors()
        return [s for s in all_sectors if s.startswith("TGN") and "sync" not in s.lower()]


# 全局客户端实例
_client: Optional[QMTClient] = None


def get_qmt_client() -> QMTClient:
    global _client
    if _client is None:
        _client = QMTClient()
    return _client
