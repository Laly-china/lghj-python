"""MyBatis-Plus 分页对象 Page 的 JSON 序列化等价实现。

对应复现原 Java：
- com.baomidou.mybatisplus.extension.plugins.pagination.Page（3.5.7）经 Jackson
  序列化后的字段集合：records/total/size/current/orders/searchCount/
  optimizeCountSql/countId/maxLimit/hitCount/pages

管理端分页接口（/api/admin/blog/page、/api/admin/blog/comments/page、
/api/admin/stock/page）原样返回 Page 对象，本工具保持相同 JSON 结构；
注意与 PageResult{total,totalPage,pageNum,pageSize,list}（/api/admin/user 分页）
是两种不同的响应结构，不可混用。
"""

from __future__ import annotations

import math
from typing import Any


def page_to_dict(
    records: list[Any],
    total: int,
    page_num: int,
    page_size: int,
) -> dict[str, Any]:
    """构造与原 Page 对象 Jackson 输出一致的字典。

    :param records: 当前页记录（实体需带 to_result_dict()，或已是 dict）
    :param total: 总记录数（对应 Page.total）
    :param page_num: 当前页码（对应 Page.current，调用方保证 >=1）
    :param page_size: 每页条数（对应 Page.size）
    """
    # 对应 Page.getPages()：size=0 时为 0，否则向上取整
    if page_size <= 0:
        total_page = 0
    else:
        total_page = math.ceil(total / page_size)

    serialized: list[Any] = []
    for record in records:
        if hasattr(record, "to_result_dict"):
            serialized.append(record.to_result_dict())
        else:
            serialized.append(record)

    return {
        "records": serialized,
        "total": total,
        "size": page_size,
        "current": page_num,
        "orders": [],
        "searchCount": True,
        "optimizeCountSql": True,
        "countId": None,
        "maxLimit": None,
        "pages": total_page,
        "hitCount": False,
    }
