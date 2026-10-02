"""统一响应体与错误码模块。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/pojo/dto/Result.java
- feng-lghj/lghj-server/src/main/java/com/lghj/enums/ErrorEnum.java

Result 结构：{code, msg, data}，全部码值/文案照抄原 ErrorEnum。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ErrorEnum(Enum):
    """全局错误枚举（照抄 com/lghj/enums/ErrorEnum.java，含原文件的重复/不规范码值）。"""

    # ====================== 通用错误 ======================
    SUCCESS = (200, "操作成功")
    NO_LOGIN = (401, "未登录，无法访问")
    SYSTEM_ERROR = (500, "系统内部异常，请稍后重试")

    # ====================== 参数错误（10000开头） ======================
    PARAM_NULL = (10001, "参数不能为空")
    PARAM_INVALID = (10002, "参数格式无效")
    USERNAME_EMPTY = (10003, "用户名不能为空")

    # ====================== 用户管理（20000开头） ======================
    USERNAME_EXIST = (20001, "用户名已存在，无法新增")
    USER_NOT_EXIST = (20002, "用户不存在，无法操作")
    USER_STATUS_INVALID = (20003, "用户状态无效，只能是0（禁用）或1（启用）")
    USER_SAVE_FAIL = (20004, "用户新增失败，数据库操作异常")
    USER_ADD_FAIL = (20005, "新增用户失败")
    USER_REMOVE_FAIL = (20006, "删除用户失败")
    USER_SELECT_BY_ID = (20006, "根据id查询用户失败")  # 原文件即为重复码值，照抄
    USER_UPDATE_FAIL = (2007, "修改用户失败")  # 原文件码值即为 2007，照抄
    USER_STATE_EX_FAIL = (20008, "修改账号状态失败")
    USER_NOT_FOUND = (20009, "账号不存在")
    PASSWORD_ERROR = (20010, "密码错误")
    ACCOUNT_LOCKED = (20011, "账号被锁定")
    NO_PERMISSION = (20012, "无管理员权限，无法访问该接口")

    # ====================== 博客管理（30000开头） ======================
    BLOG_SAVE_FAIL = (30001, "新增博客失败")
    BLOG_NOT_EXIST = (30002, "博客不存在")
    BLOG_NO_PERMISSION = (30003, "无权限删除他人博客")
    BLOG_DEL_FAIL = (30004, "博客删除失败")
    BLOG_UPDATE_FAIL = (30005, "博客编辑失败")
    BLOG_PARENT_COMMENT_NOT_FOUND = (30006, "父评论不存在或已被禁用/删除")
    BLOG_COMMENT_MISMATCHING = (30007, "二级评论与父评论不属于同一博客")
    BLOG_COMMENT_SAVE_FAIL = (30008, "评论发表失败，请稍后再试")
    BLOG_COMMENT_NOT_FOUND = (30009, "评论不存在或已被禁用/删除")
    BLOG_COMMENT_DELETE_FAIL = (30010, "评论删除失败，请稍后再试")

    # ====================== 股票数据管理（40000开头） ======================
    STOCK_QUERY_FAIL = (40001, "获取股票数据失败")

    # ====================== 交易管理（50000开头） ======================
    DONT_HAVE_ENOUGH_MONEY = (50001, "账户可用资金不足")
    POSITION_NOT_ENOUGH = (50002, "持仓不足")
    POSITION_UPDATE_FAIL = (50003, "更新持仓失败，可能存在并发操作")
    ACCOUNT_UPDATE_FAIL = (50004, "更新账户失败，可能存在并发操作")
    ACCOUNT_NOT_FOUND = (50005, "用户账户不存在")

    def __init__(self, code: int, msg: str) -> None:
        self.code = code
        self.msg = msg


class Result(BaseModel):
    """统一返回结果类（照抄 com/lghj/pojo/dto/Result.java）。"""

    # 响应状态码（200=成功，其他=失败）
    code: int
    # 响应提示信息
    msg: str
    # 响应数据（成功时返回，失败时可null）
    data: Any = None

    @staticmethod
    def _clean(data: Any) -> Any:
        """将内部对象转为可 JSON 序列化结构（对应 Jackson 序列化）。"""
        if data is None or isinstance(data, (str, int, float, bool)):
            return data
        if isinstance(data, BaseModel):
            return data.model_dump()
        if hasattr(data, "to_result_dict"):
            return data.to_result_dict()
        if isinstance(data, (list, tuple, set)):
            return [Result._clean(item) for item in data]
        if isinstance(data, dict):
            return {str(k): Result._clean(v) for k, v in data.items()}
        return data

    # ====================== 成功响应（重载方法） ======================
    @classmethod
    def success(cls, data: Any = None, msg: str | None = None) -> "Result":
        """对应 Result.success() / Result.success(Object data) / Result.success(String msg)。

        Java 通过重载区分：传字符串且作为 msg 时用 success(String msg)。
        本处约定：显式传入 msg 时走 success(String msg) 分支。
        """
        if msg is not None:
            return cls(code=ErrorEnum.SUCCESS.code, msg=msg, data=None)
        return cls(code=ErrorEnum.SUCCESS.code, msg=ErrorEnum.SUCCESS.msg, data=cls._clean(data))

    # ====================== 失败响应（对接错误枚举） ======================
    @classmethod
    def error(cls, msg: str | ErrorEnum | None = None, detail: str | None = None) -> "Result":
        """对应 Result.error(String msg) / Result.error(ErrorEnum) / Result.error(ErrorEnum, String)。

        - msg 为 str：code=500（照抄原 Result.error(String msg)）
        - msg 为 ErrorEnum 且带 detail：msg = 枚举.msg + "：" + detail（照抄拼接逻辑）
        """
        if isinstance(msg, ErrorEnum):
            if detail is not None:
                return cls(code=msg.code, msg=f"{msg.msg}：{detail}", data=None)
            return cls(code=msg.code, msg=msg.msg, data=None)
        # Result.error(String msg) 固定 code=500
        return cls(code=500, msg=str(msg or ""), data=None)
