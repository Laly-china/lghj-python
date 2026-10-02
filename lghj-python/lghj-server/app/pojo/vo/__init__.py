"""响应 VO 包（pydantic 模型，字段名照原 Java）。

对应复现原 Java com/lghj/pojo/vo 包。
"""

from app.pojo.vo.login_vo import LoginVO
from app.pojo.vo.stock_doc import StockDoc
from app.pojo.vo.stock_follow_vo import StockFollowVO
from app.pojo.vo.stock_news_vo import StockNewsVO

__all__ = ["LoginVO", "StockDoc", "StockFollowVO", "StockNewsVO"]
