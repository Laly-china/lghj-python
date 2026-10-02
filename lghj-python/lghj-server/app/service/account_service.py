"""模拟账户业务。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/service/IAccountService.java
- feng-lghj/lghj-server/src/main/java/com/lghj/service/impl/AccountServiceImpl.java
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.common.constants import SIM_ACCOUNT_INITIAL_CASH
from app.mapper import sim_account_mapper, user_position_mapper
from app.pojo.entity import SimAccount, UserPosition

# 初始资金 INITIAL_CASH = 200000.00
INITIAL_CASH = Decimal(SIM_ACCOUNT_INITIAL_CASH)
ZERO = Decimal("0.00")


def create_account(db: Session, user_id: int) -> SimAccount:
    """创建用户模拟账户（对应 AccountServiceImpl.createAccount）。

    已有账户则直接返回；新账户初始资金 200000.00，乐观锁版本号初始为 1。
    """
    existing = get_account_by_user_id(db, user_id)
    if existing is not None:
        return existing

    account = SimAccount(
        user_id=user_id,
        total_cash=INITIAL_CASH,
        available_cash=INITIAL_CASH,
        frozen_cash=ZERO,
        total_asset=INITIAL_CASH,
        version=1,  # 初始版本号，用于乐观锁
    )
    sim_account_mapper.insert_account(db, account)
    db.commit()
    return account


def get_account_by_user_id(db: Session, user_id: int) -> SimAccount | None:
    """获取用户的模拟账户（对应 getAccountByUserId，过滤 is_deleted=0）。"""
    return sim_account_mapper.select_one_by_user_id(db, user_id)


def get_user_positions(db: Session, user_id: int) -> list[UserPosition]:
    """获取用户的持仓列表（对应 getUserPositions，过滤 is_deleted=0）。"""
    return user_position_mapper.select_list_by_user(db, user_id)


def get_user_position_by_symbol(db: Session, user_id: int, symbol: str) -> UserPosition | None:
    """获取用户对特定股票的持仓（对应 getUserPositionBySymbol）。"""
    return user_position_mapper.select_one_by_user_and_symbol(db, user_id, symbol)
