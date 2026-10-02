"""A 股 Excel 数据独立导入脚本。

对应复现原 Java 入口：
- feng-lghj/lghj-server/src/main/java/com/lghj/controller/admin/StockController.java 的
  POST /api/admin/stock/import（StockServiceImpl#importStockBasic + StockExcelListener）
- 目标数据：feng-lghj/excel/A股详细数据.xlsx（EasyExcel 列索引照抄 StockExcel.java）

用法（在任意目录执行均可）：
  "...python.exe" scripts/股票导入-import-stocks.py [Excel路径]

不传路径时按原 resolveExcelPath 优先级解析：
  1. 环境变量 LGHJ_STOCK_EXCEL_PATH
  2. 相对路径 excel/A股详细数据.xlsx
  3. 原仓库 feng-lghj/excel/A股详细数据.xlsx

scripts/ 目录不作为 Python 包，脚本内自行初始化 sys.path 后导入 app 包。
"""

from __future__ import annotations

import os
import sys

# ---- sys.path 初始化：把 lghj-server 目录加入模块搜索路径 ----
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVER_ROOT = os.path.dirname(_SCRIPT_DIR)
if _SERVER_ROOT not in sys.path:
    sys.path.insert(0, _SERVER_ROOT)

from app.database import SessionLocal, engine  # noqa: E402
from app.pojo.entity import StockBasic  # noqa: E402
from app.service import stock_service  # noqa: E402


def main() -> int:
    excel_path = sys.argv[1] if len(sys.argv) > 1 else stock_service.resolve_excel_path()
    if not os.path.exists(excel_path):
        print(f"[股票导入] Excel 文件不存在：{excel_path}")
        return 1

    print(f"[股票导入] 使用 Excel：{excel_path}")
    db = SessionLocal()
    try:
        msg = stock_service.import_stock_basic(db, excel_path)
        print(f"[股票导入] 接口语义结果：{msg}")
        total = db.query(StockBasic).count()
        print(f"[股票导入] stock_basic 当前行数：{total}")
        return 0 if msg == "成功导入股票数据" else 2
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
