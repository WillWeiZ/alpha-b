# 同花顺概念板块数据获取

import akshare as ak
import pandas as pd
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ConceptInfo:
    """概念板块信息"""
    name: str  # 同花顺概念名称
    ths_code: str  # 同花顺代码
    qmt_code: str  # QMT 板块代码 (TGN开头)


class AkshareClient:
    """同花顺/akshare 客户端"""

    def __init__(self):
        self._concept_map: Optional[Dict[str, str]] = None  # name -> ths_code

    def get_concept_list(self) -> pd.DataFrame:
        """获取同花顺概念板块列表"""
        return ak.stock_board_concept_name_ths()

    def get_concept_hist(self, concept_name: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取概念板块历史K线

        Args:
            concept_name: 概念名称，如 "阿里巴巴概念"
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD

        Returns:
            DataFrame: 日期, 开盘价, 最高价, 最低价, 收盘价, 成交量, 成交额
        """
        df = ak.stock_board_concept_index_ths(
            symbol=concept_name,
            start_date=start_date,
            end_date=end_date
        )
        # 转换日期格式
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.rename(columns={
                '日期': 'date',
                '开盘价': 'open',
                '最高价': 'high',
                '最低价': 'low',
                '收盘价': 'close',
                '成交量': 'volume',
                '成交额': 'amount'
            })
        return df

    def get_concept_info(self, concept_name: str) -> Dict:
        """获取概念板块简介"""
        return ak.stock_board_concept_info_ths(symbol=concept_name)

    def map_qmt_to_ths(self, qmt_sector: str) -> Optional[str]:
        """
        QMT板块代码映射到同花顺概念名称

        QMT: TGNAI PC -> 同花顺: AI PC
        去掉 TGN 前缀即可
        """
        if qmt_sector.startswith("TGN"):
            ths_name = qmt_sector[3:]  # 去掉 TGN
            return ths_name
        return None


# 全局实例
_akshare_client: Optional[AkshareClient] = None


def get_akshare_client() -> AkshareClient:
    global _akshare_client
    if _akshare_client is None:
        _akshare_client = AkshareClient()
    return _akshare_client
