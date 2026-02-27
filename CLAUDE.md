# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Alpha B is a quantitative trading signal system for A-shares (Chinese stocks) that follows a "Hot→Boiling" trend trading philosophy. The system generates deterministic, reproducible trading signals through a rule-based engine, with LLMs only providing audit and parameter tuning suggestions.

**Core Principle**: Same inputs must produce same outputs (reproducible, backtestable).

## Key Commands

### Run the Streamlit Dashboard
```bash
cd /Users/willbot/projects/00_Alapha_B
streamlit run app.py
```

### Data Synchronization
```bash
# Incremental daily sync (recommended)
python3 data/daily_sync.py

# Quick sync for testing
python3 data/quick_sync.py

# Sync single stock
python3 data/sync_single.py <stock_code>
```

### Generate Trading Signals
```python
import sys
sys.path.insert(0, '/Users/willbot/projects/00_Alapha_B')

# T-1 Plan (post-market)
from signals import generate_plan, save_plan
plan = generate_plan(top_sectors=5, top_stocks_per_sector=3)
save_plan(plan)

# Auction Gate (09:25)
from signals import generate_auction_gate, save_auction_gate
gate = generate_auction_gate(plan)
save_auction_gate(gate)

# Intraday Decision
from signals import generate_decision, save_decision
decision = generate_decision(positions, watchlist)
save_decision(decision)
```

### QuestDB Queries
```bash
# Check data counts
curl -s 'http://localhost:9019/exec?query=SELECT count(*) FROM daily_bars'
curl -s 'http://localhost:9019/exec?query=SELECT count(*) FROM concept_bars'
curl -s 'http://localhost:9019/exec?query=SELECT max(ts) FROM daily_bars'
```

## Architecture

### Three-Layer Signal Generation Pipeline

```
QMT Gateway / Akshare → QuestDB → features/ → signals/ → JSON outputs
```

1. **data/** - Data acquisition and storage
   - `qmt_client.py` - QMT Gateway API (trading data, snapshots)
   - `akshare_client.py` - Concept sector data from Tonghuashun
   - `questdb_client.py` - Time-series database queries
   - `daily_sync.py` - Daily incremental sync script

2. **features/** - Feature calculations (pure functions, testable)
   - `utils.py` - Technical indicators (EMA, SMA, RSI, percentile_rank)
   - `market.py` - `MarketHeatResult` - Market heat (trend, breadth, extremes, liquidity)
   - `sector.py` - `SectorHeatResult` - Sector heat (RS, diffusion, participation)
   - `stock.py` - `StockHeatResult` - Stock heat (RS, RVOL, pullback quality)

3. **signals/** - Rule-based signal engine
   - `plan.py` - T-1 post-market plan generation
   - `auction_gate.py` - T0 09:25 auction gate (GREEN/YELLOW/RED)
   - `decision.py` - Intraday decisions (BUY/SELL/REDUCE/HOLD/CANCEL_PLAN)

### Output JSON Files

| File | Generated | Purpose |
|------|-----------|---------|
| `plan.json` | T-1 post-market | Market heat, candidate sectors, candidate stocks, entry triggers |
| `auction_gate.json` | T0 09:25 | Market/sector/stock gates, permission overrides |
| `decision.json` | Intraday every 5min | Actions for positions and watchlist |

### Market Heat 7-State System

The `MarketHeat` score (0-100) maps to 7 states:
- **冻** (Frozen): 0-10% - No new entries
- **寒** (Cold): 10-25% - Cautious
- **凉** (Cool): 25-40% - Reduce position
- **平** (Neutral): 40-60% - Normal
- **温** (Warm): 60-75% - Hold positions
- **热** (Hot): 75-90% - Can add positions
- **沸** (Boiling): 90-100% - Protect profits

### Risk Modes

- **SAFE**: MarketHeat < 25 or limit_spread < -10
- **CAUTIOUS**: MarketHeat < 50 or no trend structure
- **AGGRESSIVE**: Other cases

## External Dependencies

| Service | Address | Purpose |
|---------|---------|---------|
| QMT Gateway | 192.168.31.147:8080 | Trading data, real-time quotes |
| QuestDB | localhost:9019 (HTTP), 8812 (PG) | Time-series storage |
| Akshare | api.akshare.xyz | Concept sector data |

## Data Tables (QuestDB)

| Table | Description |
|-------|-------------|
| `daily_bars` | Daily OHLCV for stocks |
| `index_bars` | Daily OHLCV for indices |
| `concept_bars` | Daily OHLCV for concept sectors |
| `concept_constituents` | Sector membership mapping |

## Stock Code Format

- Shanghai: `600000.SH`
- Shenzhen: `000001.SZ`
- Beijing: `430047.BJ`

## Trading Hours (A-shares)

- Auction: 09:15 - 09:25
- Morning: 09:30 - 11:30
- Afternoon: 13:00 - 15:00
- Post-market processing: 15:00 - 16:00

## Key Weightings

### MarketHeat
- Trend: 25%, Breadth: 35%, Extremes: 25%, Liquidity: 15%

### SectorHeat
- RS: 40%, Diffusion: 40%, Participation: 20%

### StockHeat
- RS: 35%, RVOL: 25%, Pullback: 25%, SectorDiffusion: 15%

## Cron Setup

```bash
# Daily sync at 17:00, 19:00, 21:00, 23:00 on weekdays
0 17,19,21,23 * * 1-5 /usr/bin/python3 /Users/willbot/projects/00_Alapha_B/data/daily_sync.py >> /tmp/daily_sync_cron.log 2>&1
```

## References

- `docs/ARCHITECTURE.md` - Detailed architecture and data flow
- `PRD.md` - Product requirements and indicator calculation specifications
