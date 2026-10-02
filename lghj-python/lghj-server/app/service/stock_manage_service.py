"""管理端股票数据业务（分页查询/单条更新/Excel 批量更新）。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/IStockService.java
  中 pageQuery / updateByCode / batchUpdateFromExcel
- feng-lghj/lghj-server/src/main/java/com/lghj/listener/StockUpdateListener.java
  （Excel 批量更新监听器）

说明：
- ES 相关的 syncData/initDataFromExcel 属 ES 简化范围（搜索用 MySQL LIKE 替代），
  在 controller 层做等价占位实现，不在本文件。
- Excel 读取复用任务A 的 stock_service.read_excel_rows / resolve_excel_path。
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.mapper import stock_manage_mapper
from app.pojo.entity import StockBasic
from app.service import stock_service

logger = logging.getLogger(__name__)


def page_query(db: Session, page_num: int, page_size: int, keyword: str | None) -> dict:
    """分页查询股票列表（对应 pageQuery，返回 MyBatis-Plus Page 结构）。"""
    records, total = stock_manage_mapper.select_page_by_keyword(
        db, page_num, page_size, keyword
    )
    from app.common.mp_page import page_to_dict

    return page_to_dict(records, total, max(1, page_num), max(1, page_size))


def update_by_code(db: Session, body: dict) -> bool:
    """根据股票代码更新股票信息（对应 updateByCode）。

    :param body: @RequestBody StockBasic 反序列化结果（驼峰键，None 表示未传），
                 非空字段进 SET（对应 update-strategy: not_null）
    """
    values = _body_to_values(body)
    symbol = values.pop("symbol", None)
    success = stock_manage_mapper.update_by_symbol(db, symbol, values)
    if success:
        db.commit()
    return success


def batch_update_from_excel(db: Session) -> None:
    """根据 Excel 批量更新股票信息（对应 batchUpdateFromExcel + StockUpdateListener）。

    每行按 symbol 定位更新非空字段；整体逐批提交（对齐原 Listener 每
    BATCH_COUNT=100 行触发一次 batchUpdate，批量内逐条 update 语义）。
    """
    excel_path = stock_service.resolve_excel_path()
    logger.info("Start batch updating stock Excel: %s", excel_path)
    stock_list = stock_service.read_excel_rows(excel_path)

    batch: list[StockBasic] = []
    for stock in stock_list:
        batch.append(stock)
        if len(batch) >= stock_service.BATCH_COUNT:
            _batch_update(db, batch)
            batch = []
    if batch:
        _batch_update(db, batch)
    logger.info("股票基础数据批量更新完成")


def _batch_update(db: Session, stocks: list[StockBasic]) -> None:
    """逐条按代码更新（对应 StockUpdateListener.batchUpdate 的逐条 update）。"""
    for stock in stocks:
        values = {
            "name": stock.name,
            "short_name": stock.short_name,
            "total_shares": stock.total_shares,
            "float_shares": stock.float_shares,
            "total_market_cap": stock.total_market_cap,
            "float_market_cap": stock.float_market_cap,
            "industry": stock.industry,
            "market_type": stock.market_type,
            "list_date": stock.list_date,
            "is_deleted": stock.is_deleted,
        }
        stock_manage_mapper.update_by_symbol(db, stock.symbol, values)
    db.commit()
    logger.info("批量更新 %d 条股票基础数据", len(stocks))


def _body_to_values(body: dict) -> dict:
    """请求体驼峰键 → 实体列（仅非空字段，对应 BeanUtils 拷贝 + 非空更新策略）。"""
    field_map = {
        "symbol": "symbol",
        "name": "name",
        "shortName": "short_name",
        "totalShares": "total_shares",
        "floatShares": "float_shares",
        "totalMarketCap": "total_market_cap",
        "floatMarketCap": "float_market_cap",
        "industry": "industry",
        "marketType": "market_type",
        "listDate": "list_date",
        "updateTime": "update_time",
    }
    values: dict = {}
    for json_key, column in field_map.items():
        value = body.get(json_key)
        if value is None:
            continue
        if column == "list_date" and isinstance(value, str):
            # 上市日期（Jackson Date/LocalDate 默认输出 yyyy-MM-dd）
            values[column] = _parse_date(value)
        elif column == "update_time" and isinstance(value, str):
            values[column] = datetime.fromisoformat(value)
        else:
            values[column] = value
    return values


def _parse_date(value: str) -> date:
    """解析 yyyy-MM-dd（宽容兼容 ISO 日期时间前缀）。"""
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"日期格式无效: {value}") from exc
