# Alpha B 量化系统 - Streamlit 前端
#
# 数据来源:
# - 历史K线数据: QuestDB
# - 实时数据: QMT Gateway (需要连接)

import streamlit as st
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data import get_qmt_client, get_questdb_client
from features import (
    calculate_market_heat, calculate_sector_heat, calculate_stock_heat,
    get_composite_market_heat, calculate_multi_index_heat
)
from signals import generate_plan, generate_decision, decision_to_json

# 页面配置
st.set_page_config(
    page_title="Alpha B 量化系统",
    page_icon="📈",
    layout="wide"
)

# 标题
st.title("📈 Alpha B 量化交易信号系统")
st.markdown("---")

# 侧边栏 - 设置
with st.sidebar:
    st.header("⚙️ 设置")

    # QMT 连接状态
    st.subheader("QMT 连接状态")
    try:
        qmt = get_qmt_client()
        health = qmt.health()
        if health['qmt_connected']:
            st.success("✅ QMT 已连接")
        else:
            st.error("❌ QMT 未连接")
        st.write(f"交易服务器: {'✅ 已连接' if health['trading_connected'] else '❌ 未连接 (非交易时间)'}")
    except Exception as e:
        st.error(f"❌ 连接失败: {e}")

    st.markdown("---")

    # 参数设置
    st.subheader("参数设置")
    top_sectors = st.slider("热门板块数量", 1, 10, 5)
    top_stocks = st.slider("每板块个股数量", 1, 10, 3)

# ==================== 大盘环境 ====================
st.header("🌍 大盘环境 (MarketHeat)")

col1, col2, col3, col4 = st.columns(4)

# 获取多指数数据
@st.cache_data
def get_market_data():
    qdb = get_questdb_client()
    indices = ['000001.SH', '000300.SH', '000852.SH']
    bars_dict = {}

    for idx in indices:
        df = qdb.query_daily_bars(symbol=idx, limit=300)
        if not df.empty:
            # 转换数据类型
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df.index = pd.to_datetime(df['ts'])
            bars_dict[idx] = df
    return bars_dict

try:
    bars_dict = get_market_data()

    # 计算各指数热度
    heats = calculate_multi_index_heat(bars_dict)

    # 综合热度
    composite = get_composite_market_heat(heats)

    # 显示
    with col1:
        st.metric("综合热度", f"{composite.market_heat:.1f}")
    with col2:
        state = composite.market_state_7
        emoji = {"冻": "❄️", "寒": "🥶", "凉": "🍃", "平": "➡️", "温": "🌤️", "热": "🔥", "沸": "🌋"}
        st.metric("市场7态", f"{emoji.get(state, '')} {state}")
    with col3:
        rm = composite.risk_mode
        color = {"SAFE": "green", "CAUTIOUS": "orange", "AGGRESSIVE": "red"}.get(rm, "gray")
        st.markdown(f"**风险模式**: :{color}[{rm}]")
    with col4:
        st.metric("Trend Score", f"{composite.trend_score:.1f}")

    # 指数详情
    st.subheader("各指数热度")
    idx_data = []
    for code, heat in heats.items():
        idx_data.append({
            "指数": code,
            "热度": heat.market_heat,
            "7态": heat.market_state_7,
            "趋势": heat.trend_score,
            "广度": heat.breadth_score,
            "极端": heat.extremes_score,
            "流动性": heat.liquidity_score
        })
    st.dataframe(pd.DataFrame(idx_data), use_container_width=True)

except Exception as e:
    st.error(f"获取大盘数据失败: {e}")

st.markdown("---")

# ==================== 板块轮动 ====================
st.header("🏭 板块轮动 (SectorHeat)")

# 获取概念板块列表（从 QuestDB）
try:
    qdb = get_questdb_client()
    # 数据来源: QuestDB concept_constituents 表
    all_sectors = qdb.get_concept_list()

    # 过滤年份板块
    concept_sectors = [s for s in all_sectors if not s[3:].startswith('20')]

    # 选择板块
    selected_sector = st.selectbox("选择板块", concept_sectors[:50])

    if selected_sector:
        with st.spinner("计算板块热度..."):
            result = calculate_sector_heat(selected_sector)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("板块热度", f"{result.sector_heat:.1f}")
        with col2:
            st.metric("RS Score", f"{result.rs_score:.1f}")
        with col3:
            st.metric("扩散度", f"{result.diffusion_score:.1f}")
        with col4:
            st.metric("参与度", f"{result.participation_score:.1f}")

        # 候选状态
        if result.is_candidate:
            st.success(f"✅ {selected_sector} 是轮动候选板块")
        else:
            st.info(f"ℹ️ {selected_sector} 非候选板块")

        # 获取成分股（从 QuestDB）
        stocks = qdb.get_concept_stocks(selected_sector)
        a_stocks = [s for s in stocks if s.get('stock_code', '').endswith('.SH') or s.get('stock_code', '').endswith('.SZ')]

        st.subheader(f"成分股 ({len(a_stocks)} 只)")
        st.dataframe(pd.DataFrame([
            {"代码": s.get('stock_code', ''), "名称": s.get('stock_name', '')}
            for s in a_stocks
        ]), use_container_width=True)

except Exception as e:
    st.error(f"获取板块数据失败: {e}")

st.markdown("---")

# ==================== 个股分析 ====================
st.header("📊 个股分析 (StockHeat)")

# 选择板块和个股（从 QuestDB）
try:
    qdb = get_questdb_client()
    # 数据来源: QuestDB concept_constituents 表
    all_sectors = qdb.get_concept_list()
    concept_sectors = [s for s in all_sectors if not s[3:].startswith('20')]

    col1, col2 = st.columns(2)
    with col1:
        selected_sector = st.selectbox("选择板块", concept_sectors[:30], key="stock_sector")
    with col2:
        # 从 QuestDB 获取成分股
        stocks = qdb.get_concept_stocks(selected_sector)
        a_stocks = [s for s in stocks if s.get('stock_code', '').endswith('.SH') or s.get('stock_code', '').endswith('.SZ')]
        stock_options = [f"{s.get('stock_code', '')} {s.get('stock_name', '')}" for s in a_stocks]
        selected_stock = st.selectbox("选择个股", stock_options)

    if selected_stock:
        stock_code = selected_stock.split()[0]

        with st.spinner("计算个股热度..."):
            result = calculate_stock_heat(stock_code, selected_sector)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("个股热度", f"{result.stock_heat:.1f}")
        with col2:
            st.metric("RS Score", f"{result.rs_score:.1f}")
        with col3:
            st.metric("相对量", f"{result.rvol_score:.1f}")
        with col4:
            st.metric("回踩得分", f"{result.pullback_score:.1f}")

        # 详细信息
        st.subheader("交易信号")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"**突破位置**: {result.breakout_level}")
        with col2:
            st.write(f"**回踩区域**: {result.pullback_zone}")
        with col3:
            st.write(f"**止损价**: {result.stop_price:.2f}")

        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**失效位置**: {result.invalidate_level:.2f}")
        with col2:
            st.write(f"**1R 风险**: {result.r_price:.2f}")

except Exception as e:
    st.error(f"获取个股数据失败: {e}")

st.markdown("---")

# ==================== 盘中决策 ====================
st.header("🎯 盘中决策 (Decision)")

col1, col2 = st.columns(2)

with col1:
    st.subheader("当前持仓")
    # 示例持仓
    positions = [
        {"stock_code": "600536.SH", "entry_price": 45.0, "stop_price": 42.0, "r_price": 3.0}
    ]
    st.dataframe(pd.DataFrame(positions), use_container_width=True)

with col2:
    st.subheader("关注列表")
    # 示例关注
    watchlist = [
        {"stock_code": "600745.SH", "entry_trigger": "回踩EMA20"},
        {"stock_code": "600536.SH", "entry_trigger": "突破20日高点"}
    ]
    st.dataframe(pd.DataFrame(watchlist), use_container_width=True)

# 生成决策
if st.button("🔄 生成决策信号"):
    with st.spinner("生成中..."):
        signal = generate_decision(positions=positions, watchlist=watchlist)

    st.subheader("决策结果")
    st.json(decision_to_json(signal))

st.markdown("---")

# ==================== T-1 计划 ====================
st.header("📋 T-1 计划 (Plan)")

if st.button("📋 生成今日计划"):
    with st.spinner("生成计划中..."):
        plan = generate_plan(top_sectors=5, top_stocks_per_sector=3)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("市场计划")
        st.write(f"热度: {plan.market_plan['market_heat_score']}")
        st.write(f"7态: {plan.market_plan['market_state_7']}")
        st.write(f"风险模式: {plan.market_plan['risk_mode']}")

    with col2:
        st.subheader("风险控制")
        st.write(f"最大持仓: {plan.risk_controls['max_positions']}")
        st.write(f"单票风险: {plan.risk_controls['max_single_risk']*100}%")
        st.write(f"允许新开仓: {plan.risk_controls['new_entry_allowed']}")

    st.subheader(f"板块候选 ({len(plan.sector_plans)} 个)")
    if plan.sector_plans:
        st.dataframe(pd.DataFrame(plan.sector_plans), use_container_width=True)
    else:
        st.info("暂无候选板块")

    st.subheader(f"个股候选 ({len(plan.stock_plans)} 只)")
    if plan.stock_plans:
        st.dataframe(pd.DataFrame(plan.stock_plans), use_container_width=True)
    else:
        st.info("暂无候选个股")

# 页脚
st.markdown("---")
st.caption("Alpha B 量化系统 v0.1 | 热→沸趋势交易")
