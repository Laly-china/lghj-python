"""请求 DTO 包（pydantic 模型，命名照原 Java）。

对应复现原 Java com/lghj/pojo/dto 包。
"""

from app.pojo.dto.login_dto import LoginDTO
from app.pojo.dto.page_result import PageResult
from app.pojo.dto.register_dto import RegisterDTO
from app.pojo.dto.stock_excel import StockExcel

__all__ = ["LoginDTO", "PageResult", "RegisterDTO", "StockExcel"]
