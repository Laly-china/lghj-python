"""交易账户操作组件。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/trade/TradeAccountOperator.java

乐观锁说明：原 Java 通过 MyBatis-Plus @Version + OptimisticLockerInnerInterceptor 实现，
updateById 实际执行：
    UPDATE ... SET version = {old+1} WHERE id = ? AND version = {old} AND is_deleted = 0
影响行数为 0 时抛 ACCOUNT_UPDATE_FAIL / POSITION_UPDATE_FAIL。
本实现按同样语句用 SQLAlchemy Core 显式复现，并检查影响行数。

与原 Java 的一处偏差（已在交付报告说明）：
原 TradeAccountOperator.getAccount 用 selectById(userId)（按 sim_account 主键查询，
仅当账户自增 id 恰好等于 userId 时才命中）；本实现改用按 user_id 列查询
（与 AccountServiceImpl.getAccountByUserId 一致），保证任意 userId 下都能取到账户。
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.common.exception import BusinessException
from app.common.result import ErrorEnum
from app.mapper import sim_account_mapper, user_position_mapper
from app.pojo.entity import SimAccount, UserPosition

# 每手股数（LOT_SIZE = 100，委托数量单位为"手"）
LOT_SIZE = 100


def get_account(db: Session, user_id: int) -> SimAccount | None:
    """获取用户模拟账户（对应 getAccount；按 user_id 列查询，见模块 docstring 偏差说明）。"""
    return sim_account_mapper.select_one_by_user_id(db, user_id)


def update_account(db: Session, account: SimAccount) -> None:
    """乐观锁更新账户（对应 updateAccount + MP @Version），0 行影响抛业务异常。"""
    if account.id is None or account.version is None:
        # 与原行为对齐：MP 无版本号字段值时不加版本条件（此处仅防御性兜底）
        result = db.execute(
            update(SimAccount).where(SimAccount.id == account.id).values(
                total_cash=account.total_cash,
                available_cash=account.available_cash,
                frozen_cash=account.frozen_cash,
                total_asset=account.total_asset,
            )
        )
    else:
        new_version = account.version + 1
        result = db.execute(
            update(SimAccount)
            .where(
                SimAccount.id == account.id,
                SimAccount.version == account.version,
                SimAccount.is_deleted == 0,
            )
            .values(
                user_id=account.user_id,
                total_cash=account.total_cash,
                available_cash=account.available_cash,
                frozen_cash=account.frozen_cash,
                total_asset=account.total_asset,
                version=new_version,
            )
        )
        if result.rowcount == 0:
            raise BusinessException(ErrorEnum.ACCOUNT_UPDATE_FAIL, "更新账户失败，可能存在并发操作")
        account.version = new_version


def get_position(db: Session, user_id: int, symbol: str) -> UserPosition | None:
    """查询用户对特定股票的未删除持仓（对应 getPosition）。"""
    return user_position_mapper.select_one_by_user_and_symbol(db, user_id, symbol)


def insert_position(db: Session, position: UserPosition) -> None:
    """插入持仓（对应 insertPosition）。"""
    db.add(position)
    db.flush()


def update_position(db: Session, position: UserPosition) -> None:
    """乐观锁更新持仓（对应 updatePosition + MP @Version），0 行影响抛业务异常。"""
    if position.id is None or position.version is None:
        result = db.execute(
            update(UserPosition).where(UserPosition.id == position.id).values(
                total_quantity=position.total_quantity,
                frozen_quantity=position.frozen_quantity,
                available_quantity=position.available_quantity,
                cost_price=position.cost_price,
                profit_loss=position.profit_loss,
            )
        )
    else:
        new_version = position.version + 1
        result = db.execute(
            update(UserPosition)
            .where(
                UserPosition.id == position.id,
                UserPosition.version == position.version,
                UserPosition.is_deleted == 0,
            )
            .values(
                account_id=position.account_id,
                total_quantity=position.total_quantity,
                frozen_quantity=position.frozen_quantity,
                available_quantity=position.available_quantity,
                cost_price=position.cost_price,
                profit_loss=position.profit_loss,
                version=new_version,
            )
        )
        if result.rowcount == 0:
            raise BusinessException(ErrorEnum.POSITION_UPDATE_FAIL, "更新持仓失败，可能存在并发操作")
        position.version = new_version


def delete_position(db: Session, position_id: int) -> None:
    """逻辑删除持仓（对应 deleteById；MP @TableLogic 实际执行 UPDATE is_deleted=1）。"""
    db.execute(
        update(UserPosition).where(UserPosition.id == position_id).values(is_deleted=1)
    )


def stock_quantity(lot_quantity: int) -> int:
    """手数转股数：lotQuantity * 100（对应 stockQuantity）。"""
    return lot_quantity * LOT_SIZE


def order_amount(price: Decimal, lot_quantity: int) -> Decimal:
    """订单金额 = 委托价格 × 股数（对应 orderAmount = price * stockQuantity(lotQuantity)）。"""
    return price * Decimal(stock_quantity(lot_quantity))
