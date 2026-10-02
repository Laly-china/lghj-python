"""应用配置模块。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/resources/application-dev.yml
- feng-lghj/lghj-server/src/main/java/com/lghj/properties/JwtProperties.java

默认值与主控约定的运行环境一致：
- MySQL 127.0.0.1:3306 库名 lghj，root/123456
- Redis 127.0.0.1:6379 database 8，无密码
- JWT HS256 secret=itfeng，TTL=7200000000000ms，请求头名 token（与原 application-dev.yml 一致）
- 主服务监听 127.0.0.1:8080（原 server.port=8080）

所有配置均可通过 LGHJ_ 前缀的环境变量覆盖（如 LGHJ_MYSQL_PASSWORD）。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置项（对应 application-dev.yml + JwtProperties）。"""

    model_config = SettingsConfigDict(env_prefix="LGHJ_", env_file=None, extra="ignore")

    # ---------- 服务 ----------
    host: str = "127.0.0.1"       # 监听地址
    port: int = 8080              # 原 application-dev.yml: server.port=8080

    # ---------- MySQL（对应 spring.datasource） ----------
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = "lghj"
    mysql_username: str = "root"
    mysql_password: str = "123456"
    mysql_pool_size: int = 10     # 原 druid max-active=20，Python 侧适度即可
    mysql_pool_recycle: int = 3600

    # ---------- Redis（对应 spring.redis，database 8） ----------
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 8
    redis_password: str | None = None

    # ---------- JWT（对应 lghj.jwt.*，原值原样照抄） ----------
    jwt_admin_secret_key: str = "itfeng"
    jwt_admin_ttl: int = 7200000000000      # 毫秒，原 application-dev.yml
    jwt_admin_token_name: str = "token"
    jwt_user_secret_key: str = "itfeng"
    jwt_user_ttl: int = 7200000000000       # 毫秒
    jwt_user_token_name: str = "token"

    # ---------- 外部依赖 URL（对应 com/lghj/constant/UrlConstant.java 与 StockConstant.java） ----------
    stock_news_url: str = "https://search-api-web.eastmoney.com/search/jsonp"
    stock_history_sina_kline_url: str = (
        "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    )
    stock_history_tencent_kline_url: str = "http://web.ifzq.gtimg.cn/appstock/app/kline/kline"
    realtime_quote_url: str = "http://qt.gtimg.cn/q="       # 原 StockConstant.GETREALTIMEQUOTEURL
    prediction_api_minute_url: str = "http://localhost:8001/minute/{symbol}"  # 原 UrlConstant.PREDICTION_API_MINUTE_URL

    # ---------- A 股 Excel 数据路径（对应 StockServiceImpl.resolveExcelPath） ----------
    stock_excel_path: str = ""

    @property
    def sqlalchemy_database_url(self) -> str:
        """拼接 SQLAlchemy 的 PyMySQL 连接串（对应原 jdbc:mysql://...）。"""
        return (
            f"mysql+pymysql://{self.mysql_username}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    """单例获取配置（对应 Spring 的 @ConfigurationProperties 单例语义）。"""
    return Settings()


settings = get_settings()
