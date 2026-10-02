"""委托单表数据访问。

对应复现原 Java mapper/TradeOrderMapper.java（MyBatis-Plus BaseMapper）+ TradeServiceImpl
内联的 LambdaQueryWrapper 查询 + OrderRecoveryTask 的未完成订单查询。

update_order 对齐 MyBatis-Plus updateById 语义：仅更新实体中非 null 字段（默认字段策略
NOT_NULL），按主键更新；is_deleted 为 @TableLogic 字段（null 时不参与更新）。
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.pojo.entity import TradeOrder


def _non_null_values(order: TradeOrder) -> dict:
    """收集实体非 null 字段（对应 MP updateById 的 NOT_NULL 字段策略）。

    排除主键 id 与数据库端维护的 create_time/update_time（原实体中该二字段
    由 DB 默认值/ON UPDATE 维护，MP 更新时不携带）。
    """
    values: dict = {}
    for attr in (
        "order_no", "user_id", "symbol", "direction", "price", "quantity",
        "traded_quantity", "status", "cancel_time", "is_deleted",
    ):
        value = getattr(order, attr)
        if value is not None:
            values[attr] = value
    return values


def insert_order(db: Session, order: TradeOrder) -> bool:
    """插入委托单（对应 save），flush 后回填自增主键 id。"""
    db.add(order)
    db.flush()
    return True


def select_by_id(db: Session, order_id: int) -> TradeOrder | None:
    """按主键查询未删除委托单（对应 getById，@TableLogic 自动追加 is_deleted=0）。"""
    stmt = select(TradeOrder).where(TradeOrder.id == order_id, TradeOrder.is_deleted == 0)
    return db.execute(stmt).scalar_one_or_none()


def update_order(db: Session, order: TradeOrder) -> bool:
    """按主键更新委托单非 null 字段（对应 updateById），返回是否更新到行。"""
    values = _non_null_values(order)
    if not values:
        return True
    stmt = update(TradeOrder).where(TradeOrder.id == order.id).values(**values)
    result = db.execute(stmt)
    return result.rowcount > 0


def select_user_orders(db: Session, user_id: int) -> list[TradeOrder]:
    """用户委托单列表：userId + isDeleted=0，按创建时间倒序（对应 getUserOrders）。"""
    stmt = (
        select(TradeOrder)
        .where(TradeOrder.user_id == user_id, TradeOrder.is_deleted == 0)
        .order_by(TradeOrder.create_time.desc())
    )
    return list(db.execute(stmt).scalars().all())


def select_unfinished_orders(db: Session) -> list[TradeOrder]:
    """未完成订单：状态 in (1待定, 2部分完成) 且未删除（对应 OrderRecoveryTask 查询）。"""
    stmt = (
        select(TradeOrder)
        .where(TradeOrder.status.in_([1, 2]), TradeOrder.is_deleted == 0)
    )
    return list(db.execute(stmt).scalars().all())


def select_order_page(
    db: Session,
    page_num: int,
    page_size: int,
    user_id: int | None = None,
    symbol: str | None = None,
) -> tuple[list[TradeOrder], int]:
    """分页查询委托单（对应 TradeManageController.orderPage 的 Page 查询）。

    条件：userId 可选、symbol 可选、isDeleted=0，按创建时间倒序；
    返回 (记录列表, 总数)。page_size 上限 1000（对应原 PaginationInnerInterceptor.setMaxLimit）。
    """
    page_size = min(page_size, 1000)
    conditions = [TradeOrder.is_deleted == 0]
    if user_id is not None:
        conditions.append(TradeOrder.user_id == user_id)
    if symbol is not None and symbol.strip():
        conditions.append(TradeOrder.symbol == symbol)

    base = select(TradeOrder).where(*conditions).order_by(TradeOrder.create_time.desc())
    total = db.execute(
        select(func.count()).select_from(TradeOrder).where(*conditions)
    ).scalar_one()
    records = list(
        db.execute(
            base.limit(page_size).offset((page_num - 1) * page_size)
        ).scalars().all()
    )
    return records, int(total)
