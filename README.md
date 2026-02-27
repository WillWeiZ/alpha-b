# Alpha B 量化系统

> 最后更新: 2026-02-27

## 系统目标

A 股「热→沸」趋势交易信号系统：
- 确定性规则引擎（可复现、可回测）
- T-1 计划 + T0 竞价闸门 + 盘中决策
- LLM 仅做审计与参数改进建议

---

## 系统架构

### 数据存储 (QuestDB)

| 表名 | 说明 | 数据来源 |
|------|------|----------|
| `daily_bars` | 个股日线 | QMT Gateway |
| `index_bars` | 指数日线 | QMT Gateway |
| `concept_bars` | 概念板块日线 | Akshare 同花顺 |
| `concept_constituents` | 板块成分股 | QMT Gateway |

### 数据流向

```
QMT Gateway -----> QuestDB -----> features/ -----> signals/
     |                                    |
     v                                    v
Akshare (板块)                     plan.json
                                    auction_gate.json
                                    decision.json
```

---

## 快速开始

### 1. 环境要求

- Python 3.8+
- QuestDB (本地运行在 localhost:9019)
- QMT Gateway (192.168.31.147:8080)
- akshare (需要网络访问同花顺)

### 2. 启动 QuestDB

```bash
# 使用 Docker 启动 QuestDB
docker run -d -p 9019:9019 -p 8812:8812 \
  --name questdb \
  -v /Users/willbot/projects/00_Alapha_B/data/questdb:/var/lib/questdb \
  questdb/questdb:latest

# 或使用已运行的实例
# 确保 HTTP API 在 9019 端口
```

### 3. 手动运行数据同步

```bash
# 进入项目目录
cd /Users/willbot/projects/00_Alapha_B

# 运行增量同步（推荐）
python3 data/daily_sync.py

# 查看同步日志
tail -f /tmp/daily_sync.log

# 查看同步报告
# 同步完成后会自动输出报告
```

### 4. 设置定时任务

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每周一到五 17:00, 19:00, 21:00, 23:00 执行）
0 17,19,21,23 * * 1-5 /usr/bin/python3 /Users/willbot/projects/00_Alapha_B/data/daily_sync.py >> /tmp/daily_sync_cron.log 2>&1
```

**说明：**
- 每天 17:00, 19:00, 21:00, 23:00 检查更新
- 只更新增量数据（自动检测最新日期）
- 网络不稳定时可多次重试

---

## 生成交易信号

### T-1 盘后计划

```python
import sys
sys.path.insert(0, '/Users/willbot/projects/00_Alapha_B')

# 需要先安装依赖或使用已有环境
from signals.plan import generate_plan, save_plan

# 生成计划
plan = generate_plan()

# 保存到文件
save_plan(plan)

# 输出 JSON
from signals.plan import plan_to_json
print(plan_to_json(plan))
```

### 查看数据状态

```bash
# 查看各表数据量
curl -s 'http://localhost:9019/exec?query=SELECT count(*) FROM daily_bars'
curl -s 'http://localhost:9019/exec?query=SELECT count(*) FROM index_bars'
curl -s 'http://localhost:9019/exec?query=SELECT count(*) FROM concept_bars'

# 查看最新日期
curl -s 'http://localhost:9019/exec?query=SELECT max(ts), count(DISTINCT symbol) FROM daily_bars'
curl -s 'http://localhost:9019/exec?query=SELECT symbol, max(ts) FROM index_bars GROUP BY symbol'
```

---

## 项目结构

```
/Users/willbot/projects/00_Alapha_B/
├── data/
│   ├── __init__.py
│   ├── config.py           # 系统配置
│   ├── qmt_client.py       # QMT Gateway API
│   ├── akshare_client.py   # 同花顺数据 (备选)
│   ├── questdb_client.py   # QuestDB 客户端
│   ├── daily_sync.py       # 每日同步脚本
│   └── trading_calendar.csv # A股交易日历
│
├── features/
│   ├── __init__.py
│   ├── utils.py            # 指标工具 (EMA, RSI, etc.)
│   ├── market.py           # 大盘热度 (MarketHeat)
│   ├── sector.py           # 板块热度 (SectorHeat)
│   └── stock.py            # 个股热度 (StockHeat)
│
├── signals/
│   ├── __init__.py
│   ├── plan.py             # T-1 盘后计划
│   ├── auction_gate.py     # T0 集合竞价闸门
│   └── decision.py         # 盘中决策
│
├── output/                 # 信号输出目录
└── README.md
```

---

## 数据来源说明

| 功能模块 | 数据源 | 说明 |
|----------|--------|------|
| 大盘热度 | QuestDB `index_bars` | 指数历史K线 |
| 板块热度 | QuestDB `concept_bars` | 板块历史K线 |
| 个股热度 | QuestDB `daily_bars` | 个股历史K线 |
| 概念板块列表 | QuestDB `concept_constituents` | 板块成分股 |
| 实时快照 | QMT Gateway | 盘中实时行情 |
| 集合竞价 | QMT Gateway | 竞价数据 |

---

## 已知问题

| 问题 | 说明 | 状态 |
|------|------|------|
| akshare 网络问题 | 代理不稳定导致部分板块同步失败 | 多次重试可解决 |
| DiffusionScore 简化 | 用板块涨跌代替成分股扩散度 | 待改进 |
| 市场广度数据 | 未接入实时涨跌停/上涨下跌家数 | 待接入 |
| 集合竞价数据 | 暂无专门接口 | 待改进 |

---

## 下一步计划

1. [ ] 解决 akshare 网络问题（多次重试机制）
2. [ ] 完善板块扩散度计算
3. [ ] 接入市场广度数据
4. [ ] 实现 LLM 审计模块
5. [ ] 实现回测框架
6. [ ] API + 调度系统
