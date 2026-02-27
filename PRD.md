PRD：A 股「热→沸」趋势交易信号系统（Rule-based）+ LLM 审计/改参
1. 背景与问题

你采用“极端斯坦/反脆弱”的趋势赔率交易：低胜率、高赔率，目标是捕捉少数右尾（热→沸）。
现阶段痛点：

A 股 T+1 + 日内热点切换快：盘中全市场高频扫描大多无有效动作，噪声大。

交易动作若由 LLM 决策，会导致 不可复现、不可回测、不可审计。

需要：T-1 计划 + T0 集合竞价闸门 + 盘中事件触发执行 的确定性系统；LLM只做审计告警与参数改进建议。

2. 目标（Goals）
2.1 核心目标

确定性：相同输入必须输出相同 plan/gate/decision（可复现）。

可回测：信号全部可追溯到规则与参数，支持 walk-forward。

从大盘→板块→个股：体现板块轮动与趋势“热→沸”理念。

T+1 友好：闸门优先用于取消/降级，盘中只对 watchlist/持仓做事件触发。

2.2 非目标（Non-goals）

不追求“预测涨跌”或让模型输出最终买卖判断。

不在 MVP 阶段引入复杂 ML/RL 端到端策略。

3. 输入数据资产（已具备）

账户/持仓数据

指数/个股/板块 日线 OHLCV

个股 1min/5min/tick OHLCV

全市场：上涨/下跌家数、涨跌幅分布、涨停/跌停家数

概念/行业板块：OHLCV + 集合竞价涨跌幅与量（及涨跌分布）

说明：所有技术指标（EMA/RSI 等）可由上述计算得到。

4. 系统总体设计（从输出倒推）

系统输出三份确定性 JSON：

plan.json（T-1 盘后生成）：明日计划（风险模式、候选板块、候选个股、入场触发、失效、1R、禁止行为）

auction_gate.json（T0 09:25 生成）：集合竞价闸门（市场/板块/个股 GREEN/YELLOW/RED + 权限覆盖）

decision.json（盘中每 5min 生成）：只对 watchlist+持仓产生动作（BUY/SELL/REDUCE/HOLD/CANCEL_PLAN）

LLM 的输出不进入交易链，只输出两类辅助 JSON：

audit_alerts.json：审计告警（规则矛盾、数据异常、风险暴露）

change_request.json：参数改进提案（必须是可回测的“参数/阈值/分桶/过滤器”变更）

5. 数据模型与存储（QuestDB 为主）
5.1 QuestDB 表建议（最小集）

(A) 日线表：bars_1d

ts（交易日收盘时间或日期）

symbol（tag）

open/high/low/close/volume/turnover（如有）

adj_factor（如你有复权因子；没有也可先不做）

(B) 分钟线表：bars_1m / bars_5m

ts（bar end time）

symbol（tag）

open/high/low/close/volume/turnover

(C) tick 表（可选，若量很大建议分区/冷热分层）

ts, symbol(tag), price, volume, turnover, ...（按你的数据源）

(D) 市场广度表：market_breadth_1d

ts

up_count/down_count

limit_up_count/limit_down_count

return_histogram_bins（可用 JSON 或拆列）

adv_dec_ratio 等衍生字段（可计算后写回）

(E) 板块映射：sector_membership

sector_id, symbol, start_date, end_date（处理成分变动）

(F) 板块日线：sector_bars_1d

ts, sector_id(tag), open/high/low/close/volume/turnover

(G) 集合竞价：auction_snap

ts（trade_date + 09:25:00）

level（market/sector/stock）

id（market_symbol / sector_id / symbol）

auction_chg_pct

auction_vol

(可选) auction_turnover

5.2 特征存储策略（推荐）

原始 K 线放 QuestDB（你已经有）

特征/分数建议两条路：

写回 QuestDB（features_1d / features_5m）：便于在线查询与审计

同时落 Parquet（按日分区）：便于回测批量扫描（性能更稳）

结论：QuestDB 做在线/增量，Parquet 做回测/离线。不要只靠在线 SQL 做大规模历史回测。

6. 指标计算规范（核心：分层+分时域+分位数映射）
6.1 通用规范（适用于所有指标）
6.1.1 基础定义

ret_n = close / close.shift(n) - 1

ema_n：EMA(n)

rsi_14：RSI(14)

vol_ma_n = MA(volume, n)

rvol_n = volume / vol_ma_n

percentile(x, lookback=L)：滚动窗口内的分位数映射到 0-100

score = 100 * rank(x_t within [t-L, t])

处理极值：winsorize（如 1%/99%）再算 percentile，避免极端噪声污染。

6.1.2 复权与口径

默认用 后复权（qfq） 或你系统统一口径；若暂时没有复权因子，先用不复权但要明确写在 meta.data_cutoff 里。

所有计算必须避免未来函数：只用 <= t 的数据。

6.1.3 缺失处理

缺失的 score 采用中性值 50，并在 audit_alerts 记录 DATA_MISSING_xxx。

6.2 大盘指标：MarketHeat（决定“今天是否值得出手”）

目标：构建 趋势 + 扩散 + 极端 + 参与 四因子，映射到 0-100，并用分位数映射到 7态（冻寒凉平温热沸）。

6.2.1 TrendScore（趋势结构）

输入：指数日线（建议沪深300 + 中证1000 + 上证指数三者并行）

trend_1 = I(close > ema20 > ema60)（0/1）

trend_2 = percentile(ret_20, L=252)

trend_3 = percentile(ema20 - ema60, L=252)（结构差）
合成：

TrendScore = 40*trend_1 + 30*trend_2 + 30*trend_3（结果归一到 0-100）

6.2.2 BreadthScore（赚钱效应/扩散）

输入：market_breadth_1d

adv_ratio = up_count / (up_count + down_count)

limit_spread = limit_up_count - limit_down_count

dist_score：涨跌幅分布得分（沿用你 md 逻辑，但必须输出 0-100）
合成（建议）：

BreadthScore = 40*percentile(adv_ratio,252) + 30*percentile(limit_spread,252) + 30*dist_score

6.2.3 ExtremesScore（极端结构）

ext_1 = percentile(limit_spread,252)（可与 Breadth 部分重合，但这里强调尾部）

（可选）ext_2 = percentile(max_consecutive_limitups,252)（若你能拿到连板高度）
合成：

ExtremesScore = 70*ext_1 + 30*ext_2(缺失则50)

6.2.4 LiquidityScore（参与度）

输入：全市场成交额/量（若无成交额则用总量）

liq = percentile(total_turnover,252) 或 percentile(total_volume,252)

liq_acc = percentile(total_turnover / MA(total_turnover,20),252)
合成：LiquidityScore = 60*liq + 40*liq_acc

6.2.5 MarketHeat 合成与 7态映射

MarketHeat = 0.25*Trend + 0.35*Breadth + 0.25*Extremes + 0.15*Liquidity

7态映射采用 MarketHeat 的滚动分位数（L=252）：

冻 0-10%，寒 10-25%，凉 25-40%，平 40-60%，温 60-75%，热 75-90%，沸 90-100%

输出字段（写入 features_1d / plan.json.market_plan）：

market_heat_score

market_state_7

risk_mode（由规则决定）

6.3 板块指标：SectorHeat + Rotation（决定“做哪个板块”）

目标：轮动核心是 相对强弱（RS）+ 扩散（Diffusion）+ 参与（Participation）。

6.3.1 RSScore（相对强弱）

输入：sector_bars_1d + 选定基准（如沪深300/中证1000/全市场）

rs20 = sector_ret_20 - market_ret_20

rs5 = sector_ret_5 - market_ret_5

rs_acc = rs5 - rs20

RSScore = 50*percentile(rs20,252) + 50*percentile(rs_acc,252)

6.3.2 DiffusionScore（扩散）

输入：sector_membership + 成分股日线
建议最小可行口径（不需要持仓/资金数据）：

diff_up = %成分股当日上涨

diff_ma = %成分股 close > ema20

diff_high = %成分股创20日新高
合成：

DiffusionScore = 40*percentile(diff_up,252) + 35*percentile(diff_ma,252) + 25*percentile(diff_high,252)

6.3.3 ParticipationScore（参与度）

输入：板块成交额/量

part = percentile(sector_volume,252)

part_r = percentile(sector_volume/MA(sector_volume,20),252)
合成：ParticipationScore = 60*part + 40*part_r

6.3.4 SectorHeat 合成与轮动规则

SectorHeat = 0.4*RS + 0.4*Diffusion + 0.2*Participation
轮动候选（概念板块优先）：

进入候选需满足：

SectorHeat 位于全板块前 20%

且 DiffusionScore 不低于 50（避免“龙头独舞”）

且连续保持 ≥2 天（避免一天脉冲）
输出字段：

sector_heat_score, sector_rank, diffusion_score, rs_score

6.4 个股指标：StockHeat（只在强板块里选强票）

目标：围绕你认可的三要素：相对量、回踩深度/速度、板块扩散，叠加个股相对强弱与结构过滤。

6.4.1 基础过滤（生存）

avg_turnover_20d（若无成交额则用 volume）≥阈值（参数化）

close > ema20 > ema60（结构必须是“热”的基础）

排除极端不可退出：如连续一字板、长期无量（规则化）

6.4.2 StockRS（个股相对强弱）

sr20 = stock_ret_20 - sector_ret_20

sr5 = stock_ret_5 - sector_ret_5

StockRSScore = 60*percentile(sr20,252) + 40*percentile(sr5 - sr20,252)

6.4.3 RVOL（相对量）

RVOLScore = percentile(rvol_20,252)（或用近 5 日均 RVOL）

注意：日频 RVOL 主要用于 T-1 计划，不用于盘中追涨。

6.4.4 PullbackQuality（回踩深度+速度）

定义近期高点窗口 M=20：

recent_high = rolling_max(high,20)

depth = close/recent_high - 1（越接近0越浅）

speed = bars_since_recent_high_to_local_low（近似：从新高到最近低点的 bar 数）
映射规则（建议“区间得分”，而不是线性）：

浅回撤（-2% ~ -6%）得分高

过深（<-10%）降分

过快下杀（speed 很短）降分

缓慢回踩、回升时放量（可用 rvol 或上升日量）加分
最终：

PullbackScore 输出 0-100（基于规则表或分位数）

6.4.5 SectorDiffusion 作为乘子/门槛

若 sector_diffusion_score < 50：个股最高热度封顶（例如 StockHeat cap=70），避免独舞风险。

6.4.6 StockHeat 合成

StockHeat = 0.35*StockRS + 0.25*RVOL + 0.25*Pullback + 0.15*SectorDiffusion
输出字段：

stock_heat_score

breakout_level（规则定义：如 20日高点/关键位）

pullback_zone（如 [ema20 附近 ±x%] 或前高回踩区）

invalidate_level / stop_price / R_price

7. 集合竞价闸门（Auction Gate）规范（只用：竞价涨跌幅+量）

你已确认：竞价层用于 取消/降级，不用于追涨。

7.1 竞价量相对量

auction_vol_ratio = auction_vol / MA(auction_vol,20)（cap 到 3.0）

7.2 Market Gate（RED/YELLOW/GREEN）

参数示例（都应参数化+可回测）：

market_red_gap_hard = -1.8%

market_red_gap = -1.2% 且 vol_ratio>=1.2

market_green_gap = +0.3% 且 vol_ratio>=0.9
输出：

trade_permissions.new_entries（RED=false）

unit_R_multiplier（YELLOW=0.7）

7.3 Sector Gate

rs = sector_auction_chg - market_auction_chg

RED：rs<=-0.3% 或 sector<=-0.8%且放量

GREEN：rs>=+0.3% 且 sector>=0 且 vol_ratio>=1.0

否则 YELLOW（板块内股票 entry_mode 默认为 pullback_only）

7.4 Stock Gate

rs2 = stock_auction_chg - sector_auction_chg

RED：rs2<=-0.5% 或 低开放量

YELLOW：高开幅度过大导致赔率被吃光（用 gap_over_R 判定；若缺少竞价价，用涨幅近似）

GREEN：其余（但受市场/板块 gate 约束）

8. 信号生成与输出 JSON（确定性引擎）

你之前的 plan.json / auction_gate.json / decision.json 三份 schema 可以直接沿用（已讨论过）。PRD 要求：

所有 reason_codes 必须是枚举（便于统计/复盘）

decision.json 仅对 watchlist + holdings 生成动作

执行层动作空间收缩：BUY/SELL/REDUCE/HOLD/CANCEL_PLAN

9. 回测与评估规范（塔勒布式，不谈预测）

核心评价指标（每次策略版本必出）：

R multiple 分布（每笔交易：收益 / 1R 风险）

右尾频次：P(R >= 6)（“沸”阈值参数化）

左尾控制：P(R <= -1)、最大回撤、连续亏损段长度

交易次数与出手密度（闸门应显著减少无效出手）

Walk-forward：滚动训练窗口/测试窗口（例如 252/63）

分桶检验（必须做）：

MarketHeat 五分位 × SectorHeat 五分位 × StockHeat 五分位
看右尾是否随分桶单调变厚，且左尾不显著恶化。

10. LLM 在系统中的角色（审计+改参）
10.1 audit_alerts.json（只报警，不下单）

告警类型（例）：

数据异常：竞价量为0、分布缺失、成分映射为空、突变异常

规则矛盾：市场RED但 plan 仍允许 new_entries；股票 R 定义缺失

风险暴露：单票仓位超上限、当天新开仓过多、Used_R 超 cap

质量告警：候选太拥挤（高开过大+薄量）、板块扩散低但入选

10.2 change_request.json（只提“可回测的变更”）

格式要求：

只能修改：阈值、权重、分桶、过滤器、时间窗口、cap 规则

必须附带：预期影响（减少左尾/保留右尾）、回测验证方法、潜在失效机制

11. 技术栈建议（你已装 QuestDB）
11.1 语言与核心库

Python 3.11/3.12

Polars（离线特征/回测批量计算，性能比 pandas 更稳）

pandas（少量兼容）、numpy

ta-lib（可选；MVP 先手写 EMA/RSI 避免环境坑）

pydantic v2（所有 JSON schema/配置强校验）

orjson（序列化提速）

11.2 服务与调度

FastAPI + Uvicorn：对外提供 /plan, /auction_gate, /decision, /features

APScheduler（或 cron）：

盘后跑 plan

09:25 跑 auction_gate

盘中每 5min 跑 decision

日志：loguru + 结构化 JSON log（每次 run_id 可追溯）

监控：Prometheus + Grafana（最小可先只做日志与告警）

11.3 存储与计算分层

QuestDB：在线查询、增量写入、近端分钟线读取

Parquet（本地或对象存储）：回测/离线扫描（按 trade_date 分区）

（可选）DuckDB：把 Parquet 当数据湖做回测聚合，速度极佳

11.4 代码结构（建议）

data/：QuestDB 读写、Parquet 落地、成分映射管理

features/：market/sector/stock 特征计算（纯函数+可测试）

signals/：plan/gate/decision 规则引擎（确定性）

execution/：broker adapter（下单/持仓同步）

llm_audit/：审计与改参（不影响交易链）

backtest/：R multiple 评估、分桶统计、walk-forward

schemas/：pydantic models + jsonschema 导出