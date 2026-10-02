"""全局常量模块。

对应复现原 Java（feng-lghj/lghj-server/src/main/java/com/lghj/）：
- constant/JwtClaimsConstant.java
- constant/RedisConstant.java
- constant/StockConstant.java
- constant/UrlConstant.java
- constant/StatusConstant.java
- constant/PasswordConstant.java

所有键名/URL/取值均原样照抄。
"""

from __future__ import annotations

# ====================== JwtClaimsConstant.java ======================
JWT_CLAIMS_USER_ID = "userId"      # USER_ID
JWT_CLAIMS_USER_TYPE = "userType"  # USER_TYPE

# ====================== StatusConstant.java ======================
STATUS_ENABLE = 1   # ENABLE
STATUS_DISABLE = 0  # DISABLE

# ====================== PasswordConstant.java ======================
DEFAULT_PASSWORD = "123456"

# ====================== RedisConstant.java（Phase 1 用到的键前缀） ======================
# 股票实时数据缓存Key前缀
REDIS_STOCK_REAL_TIME_KEY = "stock:realtime:"
# 股票历史K线数据缓存Key前缀
REDIS_STOCK_HISTORY_KEY = "stock:history:v2:"
# 用户自选股Key前缀：user:stock:follow:{userId}
REDIS_FOLLOW_PREFIX = "user:stock:follow:"
# 缓存锁前缀，防止缓存击穿 lock:stock:minute:{market+code}
REDIS_LOCK_PREFIX = "lock:stock:minute:"
# 分时数据缓存Key前缀（RealTimeStockServiceImpl.REDIS_KEY_PREFIX）
REDIS_MINUTE_KEY_PREFIX = "stock:minute:"
# 分时数据刷新时间Key前缀（RealTimeStockServiceImpl 内联定义）
REDIS_MINUTE_UPDATETIME_PREFIX = "stock:minute:updatetime:"

# ====================== RealTimeStockServiceImpl 内部常量 ======================
# 过期时间，单位小时（EXPIRE_TIME = 24）
STOCK_CACHE_EXPIRE_HOURS = 24
# 缓存刷新时间（秒），小于这个时间则认为是新鲜数据（REFRESH_INTERVAL = 60）
MINUTE_REFRESH_INTERVAL_SECONDS = 60
# 分时数据分布式锁时长（setIfAbsent(lockKey, "1", 10, TimeUnit.SECONDS)）
MINUTE_LOCK_LEASE_SECONDS = 10

# ====================== StockConstant.java ======================
GET_REAL_TIME_QUOTE_URL = "http://qt.gtimg.cn/q="

# ====================== UrlConstant.java ======================
STOCK_NEWS_URL = "https://search-api-web.eastmoney.com/search/jsonp"
PREDICTION_API_MINUTE_URL = "http://localhost:8001/minute/{symbol}"
STOCK_HISTORY_SINA_KLINE_URL = (
    "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
)
STOCK_HISTORY_TENCENT_KLINE_URL = "http://web.ifzq.gtimg.cn/appstock/app/kline/kline"

# ====================== AccountServiceImpl 内部常量 ======================
# 初始模拟资金 INITIAL_CASH = 200000.00
SIM_ACCOUNT_INITIAL_CASH = "200000.00"
