# Alpha B 量化系统 - 架构与数据流设计文档

> 版本: v1.1
> 更新: 2026-02-27
> 状态: 已实现

---

## 1. 系统总体架构

### 1.1 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据源层                                       │
├─────────────────────┬─────────────────────┬───────────────────────────────┤
│    QMT Gateway      │   Akshare (同花顺)   │         QuestDB              │
│  (Windows miniQMT)  │   (概念板块数据)     │       (时序数据库)           │
│    :8080            │   api.akshare.xyz   │       :9019/:8812           │
└─────────┬───────────┴──────────┬──────────┴───────────────┬───────────────┘
          │                      │                           │
          │        REST/HTTP     │                    ILP/HTTP
          │                      │                           │
          ▼                      ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据层 (data/)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  config.py           │  qmt_client.py      │  questdb_client.py           │
│  - Settings         │  - 健康检查          │  - SQL 查询                  │
│  - get_settings()  │  - K线获取          │  - DataFrame 写入            │
│                     │  - 快照/持仓/委托   │  - 表创建                    │
│                     │  - 下单/撤单        │  - get_concept_list()        │
│                     │                     │  - get_concept_stocks()      │
├─────────────────────────────────────────────────────────────────────────────┤
│  akshare_client.py                                                       │
│  - 概念板块列表         - 板块历史K线                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           特征计算层 (features/)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│   │  utils.py    │    │  market.py   │    │  sector.py   │             │
│   │──────────────│    │──────────────│    │──────────────│             │
│   │ EMA          │    │ MarketHeat   │    │ SectorHeat   │             │
│   │ SMA          │    │ - Trend      │    │ - RS Score   │             │
│   │ RSI          │    │ - Breadth    │    │ - Diffusion  │             │
│   │ Percentile   │    │ - Extremes   │    │ - Particip.  │             │
│   │ Returns      │    │ - Liquidity  │    │              │             │
│   └──────────────┘    └──────────────┘    └──────────────┘             │
│                                                              │             │
│                                                    ┌──────────────┐     │
│                                                    │  stock.py    │     │
│                                                    │──────────────│     │
│                                                    │ StockHeat    │     │
│                                                    │ - RS         │     │
│                                                    │ - RVOL       │     │
│                                                    │ - Pullback   │     │
│                                                    │ - Breakout   │     │
│                                                    └──────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            信号引擎层 (signals/)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│   │  plan.py     │    │auction_gate.py│   │ decision.py  │             │
│   │──────────────│    │───────────────│    │──────────────│             │
│   │ T-1 盘后生成 │    │ T0 09:25生成 │    │ 盘中每5min   │             │
│   │──────────────│    │───────────────│    │──────────────│             │
│   │ plan.json    │    │auction_gate.  │    │ decision.    │             │
│   │              │    │    json       │    │    json      │             │
│   └──────────────┘    └───────────────┘    └──────────────┘             │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             前端展示层 (Streamlit)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│   app.py                                                                 │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │  大盘环境  │  板块轮动  │  个股分析  │  盘中决策  │  T-1计划   │  │
│   └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 模块职责

| 模块 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `data/config.py` | 系统配置 (Settings) | .env 文件 | 配置对象 |
| `data/qmt_client.py` | QMT Gateway API 封装 | HTTP 请求 | K线/快照/持仓 |
| `data/questdb_client.py` | QuestDB 客户端 | SQL 查询 | DataFrame |
| `data/akshare_client.py` | 同花顺数据 | Akshare API | 板块数据 |
| `features/utils.py` | 技术指标函数 | K线数据 | 指标值 |
| `features/market.py` | 大盘热度计算 | 指数K线 | MarketHeatResult |
| `features/sector.py` | 板块热度计算 | 板块K线/成分股 | SectorHeatResult |
| `features/stock.py` | 个股热度计算 | 个股K线 | StockHeatResult |
| `signals/plan.py` | T-1 计划生成 | 特征数据 | PlanSignal → plan.json |
| `signals/auction_gate.py` | 集合竞价闸门 | 竞价数据 | AuctionGateSignal |
| `signals/decision.py` | 盘中决策 | 持仓/关注列表 | DecisionSignal |

---

## 2. 数据流设计

### 2.1 完整数据流

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           T-1 盘后 (16:00 后)                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 1. 获取市场数据                                                      │
    │    - 上证指数 000001.SH (300日)                                     │
    │    - 沪深300 000300.SH (300日)                                      │
    │    - 中证1000 000852.SH (300日)                                      │
    │    数据来源: QuestDB index_bars / daily_bars                        │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 2. 计算 MarketHeat                                                  │
    │    - TrendScore (趋势结构) 25%                                      │
    │    - BreadthScore (赚钱效应) 35%                                    │
    │    - ExtremesScore (极端结构) 25%                                    │
    │    - LiquidityScore (参与度) 15%                                    │
    │    → 综合: MarketHeat = 0.25*T + 0.35*B + 0.25*E + 0.15*L        │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 3. 筛选热门板块                                                      │
    │    - 获取概念板块列表 (QuestDB concept_constituents)                 │
    │    - 过滤年份预增板块 (TGN2024xxx)                                   │
    │    - 计算每个板块 SectorHeat                                         │
    │    - 选取前 N 个候选板块                                             │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 4. 筛选板块内个股                                                    │
    │    - 获取板块成分股 (QuestDB concept_constituents)                   │
    │    - 过滤: 沪深A股 + 成交量阈值 + 多头结构                           │
    │    - 计算 StockHeat                                                  │
    │    - 选取前 M 只候选                                                 │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 5. 生成 plan.json                                                   │
    │    - market_plan: 市场热度、7态、风险模式                            │
    │    - sector_plans: 候选板块列表                                      │
    │    - stock_plans: 候选个股列表 (含止损价、触发条件)                  │
    │    - risk_controls: 风险控制参数                                     │
    │    - forbidden_actions: 禁止行为                                     │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           T-0 集合竞价 (09:25)                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 6. 获取竞价数据                                                      │
    │    - 市场竞价涨跌幅 (从 QMT Gateway get_snapshot)                   │
    │    - 板块竞价涨跌幅                                                  │
    │    - 个股竞价涨跌幅 + 竞价量                                         │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 7. 计算闸门状态                                                      │
    │    - Market Gate: RED / YELLOW / GREEN                             │
    │    - Sector Gate: RED / YELLOW / GREEN                             │
    │    - Stock Gate: RED / YELLOW / GREEN                              │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 8. 生成 auction_gate.json                                           │
    │    - market_gate: 市场闸门                                          │
    │    - sector_gates: 板块闸门列表                                     │
    │    - stock_gates: 个股闸门列表                                      │
    │    - permission_overrides: 权限覆盖                                  │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           盘中 (09:30 - 15:00) 每 5 分钟                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 9. 获取实时行情                                                      │
    │    - 持仓快照 (QMT Gateway get_snapshot)                           │
    │    - 关注列表快照                                                    │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 10. 计算决策                                                         │
    │     - 持仓: HOLD / REDUCE / SELL (止损/止盈/保护)                  │
    │     - 关注列表: BUY / CANCEL_PLAN                                   │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 11. 生成 decision.json                                              │
    │     - market_status: 市场状态                                       │
    │     - positions: 持仓决策                                           │
    │     - watchlist: 关注列表决策                                       │
    │     - actions: 动作列表 (优先级排序)                                 │
    └─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心计算逻辑

### 3.1 MarketHeat (大盘热度)

**目标**: 判断"今天是否值得出手"

```
输入:
  - 指数日线 K线 (open, high, low, close, volume)
  - 市场广度数据 (up_count, down_count, limit_up_count, limit_down_count)
  - 回看周期: L = 252 天

计算:

1. TrendScore (趋势结构) - 权重 25%
   ├── trend_1 = I(close > EMA20 > EMA60)          [0 或 1]
   ├── trend_2 = percentile(ret_20, L=252)          [0-100]
   └── trend_3 = percentile(EMA20-EMA60, L=252)     [0-100]

   TrendScore = 40*trend_1 + 30*trend_2/100 + 30*trend_3/100  [0-100]

2. BreadthScore (赚钱效应) - 权重 35%
   ├── adv_ratio = up_count / (up_count + down_count)
   ├── limit_spread = limit_up_count - limit_down_count
   └── dist_score = 涨跌幅分布得分 (默认50)

   BreadthScore = 40*adv_ratio*100 + 30*clamp(limit_spread,-50,50)+50 + 30*50  [0-100]

3. ExtremesScore (极端结构) - 权重 25%
   ├── ext_1 = limit_spread 分位
   └── ext_2 = 连板高度分位 (默认50)

   ExtremesScore = 70*ext_1 + 30*ext_2  [0-100]

4. LiquidityScore (参与度) - 权重 15%
   ├── liq = percentile(volume, L=252)
   └── liq_acc = percentile(volume/MA(volume,20), L=252)

   LiquidityScore = 60*liq + 40*liq_acc  [0-100]

综合:
  MarketHeat = 0.25*Trend + 0.35*Breadth + 0.25*Extremes + 0.15*Liquidity

7态映射:
  冻: 0-10%   寒: 10-25%   凉: 25-40%   平: 40-60%
  温: 60-75%  热: 75-90%   沸: 90-100%

风险模式:
  - SAFE: MarketHeat < 25 或 limit_spread < -10
  - CAUTIOUS: MarketHeat < 50 或 trend_1 = 0
  - AGGRESSIVE: 其他情况
```

### 3.2 SectorHeat (板块热度)

**目标**: 选出"做哪个板块"

```
输入:
  - 板块K线 (QuestDB concept_bars)
  - 基准指数K线 (用于计算相对强弱)
  - 板块成分股列表 (QuestDB concept_constituents)

计算:

1. RSScore (相对强弱) - 权重 40%
   ├── rs20 = sector_ret_20 - market_ret_20
   ├── rs5 = sector_ret_5 - market_ret_5
   └── rs_acc = rs5 - rs20

   RSScore = 50 + rs20*500 + rs_acc*200  [简化公式]

2. DiffusionScore (扩散度) - 权重 40%
   ├── diff_up = %成分股当日上涨 [需遍历成分股]
   ├── diff_ma = %成分股 close > EMA20
   └── diff_high = %成分股创20日新高

   DiffusionScore = 40*diff_up + 35*diff_ma + 25*diff_high

3. ParticipationScore (参与度) - 权重 20%
   ├── part = percentile(sector_volume, L=252)
   └── part_r = percentile(sector_volume/MA(sector_volume,20), L=252)

   ParticipationScore = 60*part + 40*part_r

综合:
  SectorHeat = 0.4*RS + 0.4*Diffusion + 0.2*Participation

轮动候选条件:
  - SectorHeat >= 80 (前20%)
  - DiffusionScore >= 50 (避免龙头独舞)
  - 连续保持 >= 2 天
```

### 3.3 StockHeat (个股热度)

**目标**: 选出"买哪只股票"

```
输入:
  - 个股日线K线 (QuestDB daily_bars)
  - 板块指数K线 (QuestDB concept_bars)
  - 入场参数 (R, 止损价等)

计算:

1. StockRS (相对强弱) - 权重 35%
   ├── sr20 = stock_ret_20 - sector_ret_20
   ├── sr5 = stock_ret_5 - sector_ret_5
   └── sr_acc = sr5 - sr20

   StockRSScore = 60*percentile(sr20) + 40*percentile(sr_acc)

2. RVOL (相对量) - 权重 25%
   rvol_20 = volume / MA(volume, 20)
   RVOLScore = percentile(rvol_20, L=252)

3. PullbackQuality (回踩质量) - 权重 25%
   ├── depth = close / recent_high - 1
   │   浅回撤 (-2% ~ -6%): 高分
   │   过深 (< -10%): 低分
   ├── speed = bars_since_recent_high
   │   过快下杀: 降分
   └── PullbackScore = 规则得分

4. SectorDiffusion (板块扩散乘子) - 权重 15%
   若板块扩散度 < 50, StockHeat 封顶 70

综合:
  StockHeat = 0.35*RS + 0.25*RVOL + 0.25*Pullback + 0.15*SectorDiffusion

信号:
  - breakout_level: 20日高点 / EMA20 / EMA60
  - pullback_zone: EMA20附近 / 偏离EMA
  - stop_price: 止损价 (通常 95% * close)
  - r_price: 1R 风险 = close - stop_price
  - entry_trigger: 回踩EMA20 / 突破20日高点
```

### 3.4 Auction Gate (集合竞价闸门)

**目标**: 盘前"取消/降级"交易

```
规则:

1. Market Gate
   RED (禁止新开仓):
   - 硬性: 市场竞价跌 >= -1.8%
   - 条件: 跌 >= -1.2% 且 vol_ratio >= 1.2

   GREEN (正常):
   - 竞价涨 >= 0.3% 且 vol_ratio >= 0.9

   YELLOW (谨慎):
   - 其他情况, unit_R_multiplier = 0.7

2. Sector Gate
   RED: rs <= -0.3% 或 sector <= -0.8% 且放量
   GREEN: rs >= 0.3% 且 sector >= 0 且 vol_ratio >= 1.0
   YELLOW: 其他, entry_mode = pullback_only

3. Stock Gate
   RED: rs2 <= -0.5% 或 低开放量
   YELLOW: 高开幅度过大 (gap_over_R > 1.5)
   GREEN: 其他
```

### 3.5 Decision (盘中决策)

**目标**: 盘中"执行/止损/止盈"

```
持仓决策:

1. 止损: current_price <= stop_price
   → SELL, reason: stop_loss

2. 止盈 (3R): pnl_r >= 3
   → REDUCE, reason: take_profit_3R

3. 市场保护 (沸态): market_state == "沸" 且 pnl_r >= 2
   → REDUCE, reason: market_hot_protect

4. 持有: 其他
   → HOLD, reason: normal

关注列表决策:

1. 闸门禁止: gate_status == "RED"
   → CANCEL_PLAN, reason: gate_red

2. 市场过冷: market_state in ["冻", "寒"]
   → CANCEL_PLAN, reason: market_cold

3. 触发买入: 满足 entry_trigger 条件
   → BUY

4. 持有: 其他
   → HOLD, reason: waiting
```

---

## 4. 数据模型

### 4.1 QuestDB 表结构

#### daily_bars (个股日线)
```sql
CREATE TABLE daily_bars (
    ts TIMESTAMP,
    symbol STRING,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    amount DOUBLE
) TIMESTAMP(ts) PARTITION BY YEAR DEDUP UPSERT KEYS (ts, symbol);
```

#### index_bars (指数日线)
```sql
CREATE TABLE index_bars (
    ts TIMESTAMP,
    symbol STRING,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    amount DOUBLE
) TIMESTAMP(ts) PARTITION BY YEAR DEDUP UPSERT KEYS (ts, symbol);
```

#### concept_bars (概念板块日线)
```sql
CREATE TABLE concept_bars (
    ts TIMESTAMP,
    concept_name STRING,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    amount DOUBLE
) TIMESTAMP(ts) PARTITION BY YEAR DEDUP UPSERT KEYS (ts, concept_name);
```

#### concept_constituents (板块成分股)
```sql
CREATE TABLE concept_constituents (
    ts TIMESTAMP,
    trade_date DATE,
    concept_name STRING,
    symbol STRING,
    symbol_name STRING
) TIMESTAMP(ts) PARTITION BY DAY DEDUP UPSERT KEYS (ts, trade_date, concept_name, symbol);
```

### 4.2 plan.json

```json
{
  "run_id": "plan_20260226_090000",
  "trade_date": "20260226",
  "market_plan": {
    "market_heat_score": 65.5,
    "market_state_7": "温",
    "risk_mode": "AGGRESSIVE",
    "trend_score": 72.3,
    "breadth_score": 68.1
  },
  "sector_plans": [
    {
      "sector_code": "TGNAI PC",
      "sector_heat": 88.7,
      "rs_score": 134.1,
      "diffusion_score": 53.4,
      "is_candidate": true
    }
  ],
  "stock_plans": [
    {
      "stock_code": "600536.SH",
      "stock_name": "中国软件",
      "sector_code": "TGNAI PC",
      "stock_heat": 75.2,
      "breakout_level": "20日高点",
      "pullback_zone": "EMA20附近",
      "stop_price": 42.50,
      "r_price": 2.50,
      "entry_trigger": "回踩EMA20"
    }
  ],
  "risk_controls": {
    "max_positions": 5,
    "max_single_risk": 0.02,
    "max_total_risk": 0.06,
    "new_entry_allowed": true,
    "reduce_allowed": true
  },
  "forbidden_actions": []
}
```

### 4.3 auction_gate.json

```json
{
  "run_id": "auction_20260226_092500",
  "trade_date": "20260226",
  "timestamp": "2026-02-26T09:25:00",
  "market_gate": {
    "gate": "GREEN",
    "new_entries": true,
    "reason": "normal",
    "unit_R_multiplier": 1.0,
    "symbol": "000001.SH"
  },
  "sector_gates": [
    {
      "sector_code": "TGNAI PC",
      "gate": "GREEN",
      "entry_mode": "full"
    }
  ],
  "stock_gates": [
    {
      "stock_code": "600536.SH",
      "gate": "GREEN",
      "action": "allowed"
    }
  ],
  "permission_overrides": {
    "new_entries": true,
    "add_positions": true,
    "reduce_positions": true,
    "unit_R_multiplier": 1.0
  }
}
```

### 4.4 decision.json

```json
{
  "run_id": "decision_20260226_100000",
  "trade_date": "20260226",
  "timestamp": "2026-02-26T10:00:00",
  "market_status": {
    "market_state": "温",
    "gate_status": "GREEN"
  },
  "positions": [
    {
      "stock_code": "600536.SH",
      "action": "HOLD",
      "reason": "normal",
      "pnl_pct": 2.5,
      "pnl_r": 1.0,
      "current_price": 47.50
    }
  ],
  "watchlist": [
    {
      "stock_code": "600745.SH",
      "action": "BUY",
      "reason": "pullback_trigger",
      "current_price": 33.20
    }
  ],
  "actions": [
    {
      "type": "BUY",
      "stock_code": "600745.SH",
      "reason": "pullback_trigger",
      "priority": 1
    }
  ]
}
```

---

## 5. 关键配置参数

### 5.1 风险参数

| 参数 | 值 | 说明 |
|------|-----|------|
| max_positions | 5 | 最大持仓数 (激进模式) |
| max_single_risk | 2% | 单票最大风险 |
| max_total_risk | 6% | 总仓位最大风险 |
| stop_loss | 5% | 默认止损比例 |
| take_profit_3R | 3R | 止盈阈值 |

### 5.2 热度阈值

| 参数 | 值 | 说明 |
|------|-----|------|
| sector_heat_top | 20% | 板块热度前20%入选 |
| diffusion_min | 50 | 扩散度最低要求 |
| stock_heat_min | 40 | 个股热度最低要求 |
| consecutive_days | 2 | 连续保持天数 |

### 5.3 闸门参数

| 参数 | 值 | 说明 |
|------|-----|------|
| market_red_hard | -1.8% | 市场硬红线 |
| market_red_soft | -1.2% | 市场红线 + 量能 |
| market_green | 0.3% | 市场绿线 |
| sector_rs_threshold | 0.3% | 板块相对强弱阈值 |

---

## 6. 外部依赖

### 6.1 Python 包

```
pandas>=2.0
numpy>=1.24
requests>=2.28
akshare>=1.12
questdb>=4.0
streamlit>=1.28
pydantic>=2.0
pydantic-settings>=2.0
```

### 6.2 外部服务

| 服务 | 地址 | 用途 |
|------|------|------|
| QMT Gateway | 192.168.31.147:8080 | 交易数据、实时行情 |
| QuestDB | localhost:9019 (HTTP), 8812 (PG) | 时序存储 |
| Akshare API | api.akshare.xyz | 概念板块数据 |

---

## 7. 待实现功能

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 市场广度数据接入 | 高 | 涨跌停家数、上涨下跌家数 |
| 集合竞价数据 | 高 | 专门的竞价接口 |
| 成分股扩散计算 | 中 | 真实计算 diff_up/diff_ma |
| LLM 审计 | 中 | audit_alerts.json |
| 回测框架 | 低 | R Multiple 统计 |
| WebSocket 实时 | 低 | 推送而非轮询 |

---

## 8. 附录

### 8.1 股票代码格式

- 上海: `600000.SH`
- 深圳: `000001.SZ`
- 北交所: `430047.BJ`

### 8.2 交易时间

- 集合竞价: 09:15 - 09:25
- 上午: 09:30 - 11:30
- 下午: 13:00 - 15:00
- 盘后处理: 15:00 - 16:00

### 8.3 7态含义

| 状态 | 含义 | 交易建议 |
|------|------|----------|
| 冻 | 极冷 | 禁止开仓 |
| 寒 | 较冷 | 谨慎 |
| 凉 | 偏冷 | 减少仓位 |
| 平 | 中性 | 正常 |
| 温 | 偏热 | 保持仓位 |
| 热 | 较热 | 可加仓 |
| 沸 | 极热 | 注意保护利润 |

### 8.4 关键代码路径

| 功能 | 文件路径 |
|------|----------|
| 大盘热度计算 | `features/market.py` → `calculate_market_heat()` |
| 板块热度计算 | `features/sector.py` → `calculate_sector_heat()` |
| 个股热度计算 | `features/stock.py` → `calculate_stock_heat()` |
| T-1 计划生成 | `signals/plan.py` → `generate_plan()` |
| 竞价闸门生成 | `signals/auction_gate.py` → `generate_auction_gate()` |
| 盘中决策生成 | `signals/decision.py` → `generate_decision()` |
| QuestDB 客户端 | `data/questdb_client.py` → `QuestDBClient` |
| QMT 客户端 | `data/qmt_client.py` → `QMTClient` |
