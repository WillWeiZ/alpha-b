# QMT Gateway API 文档

> 本文档供 Mac 端 SDK 开发参考，包含所有接口定义、数据模型和错误码。

## 目录

1. [概述](#概述)
2. [环境配置](#环境配置)
3. [认证](#认证)
4. [REST API](#rest-api)
5. [WebSocket API](#websocket-api)
6. [错误码](#错误码)
7. [数据模型](#数据模型)
8. [SDK 开发建议](#sdk-开发建议)

---

## 概述

### 架构

```
┌─────────────────┐         HTTP/WebSocket        ┌─────────────────┐
│   Mac Client    │ ◄─────────────────────────────►│ Windows Gateway │
│   (SDK)         │                                 │   (FastAPI)     │
└─────────────────┘                                 └────────┬────────┘
                                                             │
                                                             ▼
                                                    ┌─────────────────┐
                                                    │   miniQMT       │
                                                    │   (xtquant)     │
                                                    └─────────────────┘
```

### 基础信息

- **Base URL**: `http://<windows-ip>:8080`
- **Content-Type**: `application/json`
- **API Key Header**: `X-API-Key`

### 网关状态

| 状态 | 说明 |
|------|------|
| `healthy` | QMT 已连接，交易服务器已连接 |
| `degraded` | QMT 已连接但交易服务器未连接（非交易时间或 mock 模式） |
| `unhealthy` | QMT 未连接 |

---

## 环境配置

### Gateway 端 (.env)

```bash
# Server Configuration
HOST=0.0.0.0
PORT=8080
DEBUG=false

# Authentication (comma-separated for multiple keys)
API_KEYS=iloveyou,another-key

# IP Allowlist (comma-separated, empty = all allowed)
IP_ALLOWLIST=

# miniQMT Configuration
QMT_PATH=D:\迅投极速交易终端\userdata_mini
QMT_ACCOUNT_ID=40304296
QMT_ACCOUNT_TYPE=STOCK
QMT_SESSION_ID=123456
```

### SDK 端配置建议

```python
# config.py
GATEWAY_URL = "http://192.168.31.147:8080"  # Windows 主机 IP
API_KEY = "iloveyou"
TIMEOUT = 30  # 秒
WS_RECONNECT_INTERVAL = 5  # 秒
```

---

## 认证

所有接口（除 `/health`）都需要在请求头中携带 API Key：

```
X-API-Key: your-api-key
```

认证失败返回：
```json
{
  "code": 10001,
  "message": "Invalid API key",
  "trace_id": "xxx",
  "details": {}
}
```

---

## REST API

### 1. 健康检查

**GET** `/v1/health`

无需认证。

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "trace_id": "xxx",
  "data": {
    "status": "degraded",
    "qmt_connected": true,
    "trading_connected": false,
    "qmt_account_id": "40304296",
    "last_tick_time": "2026-02-15T21:04:30",
    "ws_market_clients": 0,
    "ws_trade_clients": 0,
    "uptime_seconds": 3600,
    "version": "1.0.0"
  }
}
```

---

### 2. 查询余额

**GET** `/v1/account/balance`

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "trace_id": "xxx",
  "data": {
    "account_id": "40304296",
    "account_type": "STOCK",
    "cash": 217259.74,
    "frozen_cash": 0.0,
    "market_value": 580950.0,
    "total_asset": 798209.74,
    "available_cash": 217259.74,
    "updated_at": "2026-02-15T21:04:22.459047"
  }
}
```

---

### 3. 查询持仓

**GET** `/v1/account/positions`

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| stock_code | string | 否 | 股票代码，不传则返回所有 |

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "trace_id": "xxx",
  "data": {
    "positions": [
      {
        "account_id": "40304296",
        "stock_code": "300308.SZ",
        "volume": 700,
        "can_use_volume": 700,
        "frozen_volume": 0,
        "on_road_volume": 0,
        "yesterday_volume": 700,
        "open_price": 624.49,
        "avg_price": 624.49,
        "market_value": 371700.0,
        "profit_loss": null,
        "direction": 48,
        "updated_at": "2026-02-15T21:04:22.918492"
      }
    ]
  }
}
```

**字段说明**:
| 字段 | 说明 |
|------|------|
| volume | 总持仓量 |
| can_use_volume | 可用持仓（可卖出） |
| frozen_volume | 冻结数量 |
| on_road_volume | 在途数量（买入待成交） |
| yesterday_volume | 昨日持仓（T+1 计算） |
| direction | 48=多头（股票只有多头） |

---

### 4. 查询委托

**GET** `/v1/orders`

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | ALL/OPEN，默认 ALL |
| order_id | int | 否 | 指定委托 ID |

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "trace_id": "xxx",
  "data": {
    "orders": [
      {
        "order_id": 0,
        "order_sysid": "40114",
        "account_id": "40304296",
        "stock_code": "300757.SZ",
        "order_type": 23,
        "order_type_name": "STOCK_BUY",
        "direction": "buy",
        "offset_flag": "open",
        "order_volume": 200,
        "traded_volume": 200,
        "order_price": 426.91,
        "traded_price": 426.91,
        "price_type": "FIX_PRICE",
        "order_status": 56,
        "order_status_name": "SUCCEEDED",
        "status_msg": "",
        "order_time": "2026-02-13T09:34:24",
        "strategy_name": "",
        "order_remark": "",
        "intent_id": ""
      }
    ]
  }
}
```

**order_type 常用值**:
| 值 | 名称 | 说明 |
|---|------|------|
| 23 | STOCK_BUY | 股票买入 |
| 24 | STOCK_SELL | 股票卖出 |

**order_status 状态码**:
| 值 | 名称 | 说明 |
|---|------|------|
| 48 | UNREPORTED | 未报 |
| 49 | WAIT_REPORTING | 待报 |
| 50 | REPORTED | 已报 |
| 51 | REPORTED_CANCEL | 已报待撤 |
| 52 | PARTSUCC_CANCEL | 部成待撤 |
| 53 | PART_CANCEL | 部撤 |
| 54 | CANCELED | 已撤 |
| 55 | PART_SUCC | 部成 |
| 56 | SUCCEEDED | 已成 |
| 57 | JUNK | 废单 |

---

### 5. 下单

**POST** `/v1/orders`

**请求体**:
```json
{
  "intent_id": "strategy_001_order_001",
  "stock_code": "600000.SH",
  "direction": "buy",
  "volume": 100,
  "price_type": "FIX_PRICE",
  "price": 10.5,
  "strategy_name": "my_strategy",
  "order_remark": "custom_remark"
}
```

**字段说明**:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| intent_id | string | 否 | 幂等 ID，相同 intent_id 返回已存在订单 |
| stock_code | string | 是 | 股票代码，如 "600000.SH" |
| direction | string | 是 | buy / sell |
| volume | int | 是 | 委托数量（股），必须是 100 的整数倍 |
| price_type | string | 是 | FIX_PRICE（限价）/ LATEST_PRICE（最新价） |
| price | float | 条件 | 限价时必填 |
| strategy_name | string | 否 | 策略名称 |
| order_remark | string | 否 | 备注 |

**响应（成功）**:
```json
{
  "code": 0,
  "message": "success",
  "trace_id": "xxx",
  "data": {
    "order_id": 12345,
    "intent_id": "strategy_001_order_001",
    "message": "Order placed successfully"
  }
}
```

**响应（幂等 - 订单已存在）**:
```json
{
  "code": 0,
  "message": "success",
  "trace_id": "xxx",
  "data": {
    "order_id": 12345,
    "intent_id": "strategy_001_order_001",
    "message": "Order already exists (idempotent)"
  }
}
```

**响应（非交易时间）**:
```json
{
  "code": 50003,
  "message": "Trading server not connected. This may occur during non-trading hours.",
  "trace_id": "xxx",
  "details": {
    "hint": "Wait for trading hours or check QMT client connection status"
  }
}
```

---

### 6. 撤单

**POST** `/v1/orders/cancel`

**请求体**:
```json
{
  "order_id": 12345
}
```

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "trace_id": "xxx",
  "data": {
    "order_id": 12345,
    "message": "Cancel request sent"
  }
}
```

---

### 7. 订阅行情

**POST** `/v1/market/subscribe`

**请求体**:
```json
{
  "codes": ["600000.SH", "000001.SZ"],
  "data_type": "tick"
}
```

**data_type 可选值**:
| 值 | 说明 |
|------|------|
| tick | 逐笔成交 |
| depth | 深度行情 |
| bar_1m | 1分钟K线 |
| bar_5m | 5分钟K线 |
| bar_1d | 日K线 |

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "trace_id": "xxx",
  "data": {
    "subscribed": ["600000.SH", "000001.SZ"],
    "data_type": "tick",
    "subscription_id": "sub_1771160669"
  }
}
```

---

### 8. 取消订阅

**POST** `/v1/market/unsubscribe`

**请求体**:
```json
{
  "codes": ["600000.SH"],
  "data_type": "tick"
}
```

---

### 9. 行情快照

**GET** `/v1/market/snapshot`

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 股票代码，多个用逗号分隔 |

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "trace_id": "xxx",
  "data": {
    "600000.SH": {
      "time": "2026-02-15T21:04:30.071071",
      "last_price": 9.89,
      "open": 9.98,
      "high": 10.03,
      "low": 9.88,
      "prev_close": 9.98,
      "volume": 700407,
      "amount": 696614500,
      "transaction_num": 0,
      "stock_status": 5,
      "ask_price": [9.90, 9.91, 9.92, 9.93, 9.94],
      "ask_volume": [1821, 2795, 2204, 1060, 894],
      "bid_price": [9.89, 9.88, 9.87, 9.86, 9.85],
      "bid_volume": [1630, 25534, 4845, 8487, 4170]
    }
  }
}
```

---

### 10. 历史K线

**GET** `/v1/history/bars`

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 股票代码 |
| freq | string | 是 | 周期：1m / 5m / 1d |
| start | string | 是 | 开始时间，格式：YYYYMMDD 或 YYYYMMDDHHmmss |
| end | string | 否 | 结束时间 |
| count | int | 否 | 返回条数，替代时间范围 |

**响应**:
```json
{
  "code": 0,
  "message": "success",
  "trace_id": "xxx",
  "data": {
    "code": "600000.SH",
    "freq": "1d",
    "count": 4,
    "bars": [
      {
        "time": 1770652800000,
        "open": 10.19,
        "high": 10.24,
        "low": 10.15,
        "close": 10.18,
        "volume": 464298,
        "amount": 472864734.0
      }
    ]
  }
}
```

**注意**: `time` 是毫秒级 Unix 时间戳。

---

## WebSocket API

### 连接

```
ws://<host>:8080/v1/ws/market?api_key=<your-api-key>
ws://<host>:8080/v1/ws/trade?api_key=<your-api-key>
```

### 1. 行情 WebSocket (`/v1/ws/market`)

**订阅**:
```json
{
  "type": "subscribe",
  "data": {
    "codes": ["600000.SH", "000001.SZ"],
    "data_type": "tick"
  }
}
```

**订阅确认**:
```json
{
  "type": "subscribed",
  "timestamp": "2026-02-15T21:04:35.320454",
  "data": {
    "codes": ["600000.SH"],
    "data_type": "tick"
  }
}
```

**行情推送**:
```json
{
  "type": "tick",
  "trace_id": "",
  "timestamp": "2026-02-15T21:04:36.123456",
  "data": {
    "stock_code": "600000.SH",
    "lastPrice": 9.89,
    "open": 9.98,
    "high": 10.03,
    "low": 9.88,
    "lastClose": 9.98,
    "volume": 700407,
    "amount": 696614500,
    "askPrice": [9.90, 9.91, 9.92, 9.93, 9.94],
    "askVol": [1821, 2795, 2204, 1060, 894],
    "bidPrice": [9.89, 9.88, 9.87, 9.86, 9.85],
    "bidVol": [1630, 25534, 4845, 8487, 4170]
  }
}
```

**取消订阅**:
```json
{
  "type": "unsubscribe",
  "data": {
    "codes": ["600000.SH"],
    "data_type": "tick"
  }
}
```

**心跳**:
```json
// 发送
{"type": "ping"}

// 响应
{"type": "pong", "timestamp": "2026-02-15T21:04:40.123456"}
```

**错误响应** (QMT 未连接):
```json
{
  "type": "error",
  "timestamp": "2026-02-15T21:04:35.320454",
  "data": {
    "code": 50001,
    "message": "miniQMT not connected"
  }
}
```

---

### 2. 交易事件 WebSocket (`/v1/ws/trade`)

**连接确认**:
```json
{
  "type": "connected",
  "timestamp": "2026-02-15T21:04:42.373976",
  "data": {
    "account_id": "40304296",
    "message": "Connected to trade event stream"
  }
}
```

**订单状态更新**:
```json
{
  "type": "order",
  "trace_id": "",
  "timestamp": "2026-02-15T21:04:42.373976",
  "data": {
    "order_id": 12345,
    "order_sysid": "40114",
    "account_id": "40304296",
    "stock_code": "600000.SH",
    "order_type": 23,
    "direction": "buy",
    "offset_flag": "open",
    "order_volume": 100,
    "traded_volume": 50,
    "order_price": 10.5,
    "traded_price": 10.48,
    "order_status": 55,
    "status_msg": "",
    "order_time": "2026-02-15T09:30:00"
  }
}
```

**成交回报**:
```json
{
  "type": "trade",
  "trace_id": "",
  "timestamp": "2026-02-15T21:04:42.373976",
  "data": {
    "order_id": 12345,
    "trade_id": 67890,
    "stock_code": "600000.SH",
    "direction": "buy",
    "volume": 50,
    "price": 10.48,
    "trade_time": "2026-02-15T09:30:05"
  }
}
```

**订单错误**:
```json
{
  "type": "order_error",
  "trace_id": "",
  "timestamp": "2026-02-15T21:04:42.373976",
  "data": {
    "order_id": 12345,
    "error_id": 200000,
    "error_msg": "未建立连接"
  }
}
```

**账户状态**:
```json
{
  "type": "account_status",
  "trace_id": "",
  "timestamp": "2026-02-15T21:04:42.373976",
  "data": {
    "account_id": "40304296",
    "status": 0,
    "status_name": "OK"
  }
}
```

---

## 错误码

### 错误响应格式

```json
{
  "code": 50001,
  "message": "miniQMT not connected",
  "trace_id": "xxx",
  "details": {}
}
```

### 错误码表

| 范围 | 类别 |
|------|------|
| 10000-19999 | 认证/权限错误 |
| 20000-29999 | 请求参数错误 |
| 30000-39999 | 交易相关错误 |
| 50000-59999 | 系统错误 |

### 常见错误码

| 错误码 | 名称 | 说明 | HTTP 状态码 |
|--------|------|------|-------------|
| 10001 | AuthenticationError | 无效的 API Key | 401 |
| 10002 | IPNotAllowedError | IP 不在白名单 | 401 |
| 10003 | RateLimitError | 请求频率超限 | 429 |
| 20001 | ValidationError | 参数验证失败 | 400 |
| 20002 | ResourceNotFoundError | 资源不存在 | 404 |
| 30001 | OrderRejectedError | 订单被拒绝 | 422 |
| 30002 | InsufficientBalanceError | 余额不足 | 422 |
| 30003 | OrderNotCancellableError | 订单不可撤销 | 422 |
| 50001 | QMTNotConnectedError | miniQMT 未连接 | 500 |
| 50002 | InternalError | 内部错误 | 500 |
| 50003 | TradingServerNotConnectedError | 交易服务器未连接（非交易时间） | 500 |

---

## 数据模型

### 股票代码格式

- 上海证券交易所: `600000.SH`
- 深圳证券交易所: `000001.SZ`
- 北京证券交易所: `430047.BJ`

### 时间格式

- ISO 8601: `2026-02-15T09:30:00` 或 `2026-02-15T09:30:00.123456`
- 紧凑格式（K线查询）: `20260215` 或 `20260215093000`

### 交易时间

A股交易时间（用于判断 `trading_connected` 状态）：
- 上午: 09:30 - 11:30
- 下午: 13:00 - 15:00

---

## SDK 开发建议

### 推荐项目结构

```
qmt_client/
├── __init__.py           # 导出主要类
├── client.py             # QMTClient 主类
├── http_client.py        # HTTP 请求封装
├── websocket.py          # WebSocket 客户端
├── models/
│   ├── __init__.py
│   ├── account.py        # Balance, Position
│   ├── order.py          # Order, OrderRequest
│   ├── market.py         # Tick, Bar
│   └── common.py         # 通用模型
├── exceptions.py         # 异常定义
└── constants.py          # 常量（状态码等）
```

### 异常类设计

```python
class QMTError(Exception):
    """基础异常"""
    def __init__(self, code: int, message: str, trace_id: str = None):
        self.code = code
        self.message = message
        self.trace_id = trace_id

class AuthenticationError(QMTError): pass
class QMTNotConnectedError(QMTError): pass
class TradingServerNotConnectedError(QMTError): pass
class ValidationError(QMTError): pass
class OrderRejectedError(QMTError): pass
```

### 客户端使用示例

```python
from qmt_client import QMTClient
from qmt_client.exceptions import QMTNotConnectedError

# 初始化
client = QMTClient(
    base_url="http://192.168.1.100:8080",
    api_key="iloveyou",
    timeout=30
)

# 健康检查
health = client.health()
if health["trading_connected"]:
    # 可以下单
    pass

# 查询余额
try:
    balance = client.get_balance()
    print(f"可用资金: {balance['available_cash']}")
except QMTNotConnectedError:
    print("QMT 未连接")

# 下单（带幂等性）
order = client.place_order(
    intent_id="strategy_001_20260215_001",  # 重要：幂等 ID
    stock_code="600000.SH",
    direction="buy",
    volume=100,
    price=10.5
)

# 订阅实时行情
def on_tick(tick):
    print(f"{tick['stock_code']}: {tick['last_price']}")

client.subscribe_ticks(["600000.SH"], on_tick=on_tick)

# 订阅交易事件
def on_order(order):
    print(f"订单状态: {order['order_status_name']}")

client.on_order_update(on_order)

# 保持运行
client.run_forever()
```

### 注意事项

1. **幂等性**: 下单时务必提供唯一的 `intent_id`，避免网络重试导致重复下单
2. **非交易时间**: 检查 `trading_connected` 状态，避免在非交易时间下单
3. **WebSocket 重连**: 实现 自动重连逻辑
4. **心跳**: WebSocket 连接需要定期发送 ping 保持连接
5. **错误处理**: 根据错误码决定重试策略

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-02-15 | 初始版本 |

---

## CURRENT API ENDPOINT LIST (Updated: 2026-02-21)

Source of truth: src/main.py routes.

### REST

| Method | Path | Description |
|---|---|---|
| GET | /health | Health check alias (no auth) |
| GET | /v1/health | Health check |
| GET | /v1/account/balance | Query account balance |
| GET | /v1/account/positions | Query positions |
| GET | /v1/orders | Query orders |
| GET | /v1/trades | Query today's trades |
| POST | /v1/orders | Place order |
| POST | /v1/orders/cancel | Cancel order |
| POST | /v1/market/subscribe | Subscribe market data |
| POST | /v1/market/unsubscribe | Unsubscribe market data |
| GET | /v1/instruments/detail | Query instrument detail |
| GET | /v1/market/trading-calendar | Query trading calendar |
| GET | /v1/market/sectors | Query sector list |
| GET | /v1/market/sector-stocks | Query stocks in sector |
| GET | /v1/market/snapshot | Query market snapshot |
| GET | /v1/history/bars | Query historical bars |

### WEBSOCKET

| Protocol | Path | Description |
|---|---|---|
| WS | /v1/ws/market | Market stream (tick/depth) |
| WS | /v1/ws/trade | Trade stream (order/trade events) |
