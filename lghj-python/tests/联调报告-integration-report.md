# 联调报告-integration-report（Phase 7：三服务联调 + 全量 API 契约自测）

> 执行日期：2026-10-02。范围：lghj-server(8080) / ai-agent-server(8091) / prediction-server(8001)
> 对照前端 `lghj-web-dist.tar/lghj_web`（Vue3 + vite 代理）梳理出的全量 API 契约，
> 以 pytest 契约测试逐项验证（含真实 LLM 调用与跨服务链路）。

## 一、执行环境

| 项 | 值 |
| --- | --- |
| Python | env/venv-虚拟环境（3.13.14，pytest 9.1.1） |
| MySQL / Redis | 127.0.0.1:3306 库 lghj（15 表 + 5458 只股票）/ 127.0.0.1:6379 db8（protocol=2） |
| 三服务 | 8080/8091/8001 均以 `LGHJ_INTERNAL_API_TOKEN=phase7-internal-token` 启动 |
| LLM | DeepSeek（环境已有 DEEPSEEK_API_KEY，chat/chat_stream 为**真调**） |

## 二、API 清单与覆盖率

全量清单见 `tests/API清单-api-inventory.md`（依据前端 7 个 api 模块 + vite 代理 + 视图消费点梳理）：

| 模块 | 清单数 | 已测 | 说明 |
| --- | --- | --- | --- |
| auth.js | 3 | 3 | 登录/注册/登出 |
| stock.js | 9 | 8 | `get_excel`（#9）为前端死接口——**原 Java 后端亦无该路由**（已 grep 验证），不测不复现 |
| user.js | 2 | 2 | 关注/取关、是否关注 |
| trade.js | 8 | 8 | 建户/账户/持仓/下单/撤单/委托/成交 |
| community.js | 13 | 13 | 博客 CRUD/点赞/评论树/评论点赞/Feed |
| admin.js | 12+2 | 15 | 12 个前端接口 + GET user/{id}、GET blog/{id} 详情抽测；**import（#49）未执行**——避免重复导入股票（严禁项），导入路径任务A 已自测 |
| agent.js（8091） | 3+1 | 4 | config_list / create_session(GET+POST) / chat / chat_stream |
| 内部 API（8080） | 2 | 2 | market/realtime、sim-trade/profile（含 token 三态） |
| **合计** | **57** | **55** | 2 个排除项如上；**覆盖率 55/55 = 100%（可测范围）** |

## 三、pytest 执行统计

- 测试文件：`test_auth.py`(13) / `test_stock.py`(7) / `test_trade.py`(12) / `test_community.py`(9) /
  `test_admin.py`(11) / `test_agent.py`(10) / `test_ml.py`(6)，共 **68 条用例**（另 conftest 公共夹具）。
- **第 1 轮全量：68 passed / 0 failed / 0 skipped（30.5s）**；
- **第 2 轮全量（可重复执行验证）：68 passed / 0 failed / 0 skipped（22.2s）**。
- 可重复性保障：随机用户名后缀；teardown 自清理（博客→自选股→用户逻辑删除）；
  股票 update 用原值回写（幂等）；孤儿博客（已删用户的博客）曾污染热点接口，已清理并从根上杜绝。

## 四、发现并修复的 bug（服务代码，均不改变对外契约）

### 1. lghj-server：分时跨服务取数超时过短（真实缺陷）
- **现象**：`GET /api/user/realtime/minute?market=sh&code=000001`（上证指数，Dashboard 默认标的）
  首次返回空数组 `data:[]`；8001 直连同 symbol 却有数据。
- **根因**：`real_time_stock_service._fetch_from_python_service` 调 8001 用 `timeout=5.0`；
  8001 冷启动当日首次经 akshare 采集外网分时（含落 CSV 缓存）可能超过 5s，超时被
  try/catch 语义吞掉 → 返回空数组。
- **修复**：超时 5s → 30s（文件 `lghj-server/app/service/real_time_stock_service.py`）。
  修复后冷路径实测 3s 内成功取数。
- **契约影响**：无（仅内部超时参数）。

### 2. lghj-server：内部交易画像接口对有持仓用户必崩 500（真实缺陷，阻断 8091 工具链）
- **现象**：`GET /api/internal/sim-trade/profile?userId=<有持仓用户>` → `{"code":500,"msg":"系统内部异常"}`；
  无持仓用户正常。
- **根因**：`sim_trade_profile_service._build_summary` 照抄 Java
  `BigDecimal.divide(divisor, 4, HALF_UP)` —— Python `decimal.Decimal` **没有 `divide` 方法**
  （`'decimal.Decimal' object has no attribute 'divide'`），凡走到重仓占比计算分支（有持仓）必抛
  AttributeError。此前自测未发现是因为自测用户无持仓。
- **修复**：改为 Python 等价实现 `(_position_cost / cost).quantize(Decimal("0.0001"), ROUND_HALF_UP)`
  （精度 4 位、HALF_UP 语义不变，文件 `lghj-server/app/service/sim_trade_profile_service.py`）。
  修复后有持仓用户画像正常返回（含 4 位小数 topPositionCostRatio）。
- **契约影响**：无（输出字段与精度不变）。

### 3. 测试侧修正（经与原 Java 源码逐条核对，均为**忠实原系统的行为**，不改服务代码）
| 测试假设（错） | 原系统真实契约（对） | 依据 |
| --- | --- | --- |
| 自选股列表含 followTime | StockFollowVO 仅 {stockId,symbol,name,price,changePercent,volume}；前端 Watchlist 的 currentPrice/followTime 为前端固有差异 | 原 Java StockFollowVO.java |
| order.quantity/tradedQuantity/deal.quantity 单位为股 | 均为**手**（原 `execute(order, currentPrice, order.getQuantity())` 同单位传递，LOT_SIZE=100 仅在资金/持仓结算时相乘） | 原 TradeServiceImpl#processTrade + TradeAccountOperator |
| comments/list 的 isLiked 随 token 生效 | 该端点在放行清单内，原 Java 不走 preHandle → BaseContext 为空 → isLiked 恒 0（liked 计数仍正确） | 原 WebMvcConfiguration + BlogCommentsServiceImpl |
| 热点博客对已删用户博客应正常返回 | 原 Java queryBlogUser 无判空，user 为 null 时 NPE → 500（忠实保留） | 原 BlogServiceImpl#queryBlogUser |
| 管理端删除注册用户应成功 | 注册不建 user_role 行，MP remove() 0 行返回 false → 原系统同样抛"用户-角色关联记录删除失败"（用户行已先逻辑删除） | 原 UserServiceImpl#removeUser |
| /admin/user VO 含 id/nickName | UserVO 契约无 id/nickName 字段（昵称修改仅落库） | 原 vo/UserVO.java |

## 五、端到端链路验证结论

| 链路 | 结论 | 证据 |
| --- | --- | --- |
| **8001 → 8080（分时）** | ✅ 打通 | `GET /api/user/realtime/minute?market=sh&code=600519` 返回与 8001 直连同构的分时数组（4 字段）；上证指数 sh000001 链路修复超时后打通；`/minute` 裸数组 4 字段、`/predict` 30 项 predictions 全部符合契约 |
| **8091 → 8080（agent 工具链）** | ✅ 打通（真调） | DEEPSEEK 真调下，agent chat"请查询我的模拟交易画像"触发 LLM 真实调用 `querySimTradeProfile` 工具 —— 8080 访问日志出现 `GET /api/internal/sim-trade/profile?userId=65`（200，**带正确 X-Internal-Token、数字 userId、返回真实交易数据**）；`/api/internal/market/realtime?code=600519&includeMinute=false` 同样被调用；chat 内容非空、chat_stream 为 text/plain 流式非空 |
| **X-Internal-Token 三态** | ✅ | 正确 token → 200；错误/缺失 → `code:500 "internal token invalid"`（HTTP 200，照抄原 Spring 语义）；8080/8091 双方同环境变量时链路自洽 |
| **vite 代理等价性** | ✅ | `/api/ml/*` 剥离前缀直测 8001、`/api/v1/*` 直测 8091、其余直测 8080，与 vite.config.js 一一对应 |
| **三种响应体** | ✅ | Result{code:200} / Response{code:"0000"} / 8001 裸 JSON（数组 + {symbol,predictions}）全部按前端 request.js 适配器预期返回 |

## 六、遗留问题（均为原系统固有行为或前端固有差异，不属本次缺陷）

1. **前端字段名差异（原系统固有，展示层空白但不报错）**：Watchlist 的 `currentPrice/followTime`（后端 `price`，无 followTime）、Simulation 的 `avgPrice/marketValue/profit/filledQuantity/dealTime`（后端 `costPrice/profitLoss/tradedQuantity/createTime`）、TradeManage 的 `code/name/type/count/stockCode/stockName/dealPrice/dealCount`（后端 `symbol/dealDirection/price/quantity`）。原 Java 与本工程行为一致。
2. **`/api/user/prediction/{symbol}/get_excel`**：前端有按钮、原 Java 无路由 → 导出预测 Excel 不可用（原系统同样），未复现。
3. **热点博客 500**：已删用户留下的博客会使 query/hot 抛 500（原 NPE 忠实保留）；生产上应避免只删用户不删博客。
4. **管理端删除"注册用户"** 返回 500（"用户-角色关联记录删除失败"，用户行已实际逻辑删除）；删除"管理端新增用户"（有角色行）正常 —— 原 MP remove() 语义忠实保留。
5. **agent 会话 userId 非数字**（如未登录 guest）：画像工具调用降级为空数据（原 Java 同样透传字符串 userId）；登录用户为 String(数字 id)，工具可取到真实画像。
6. **chat 工具调用为 LLM 概率行为**：测试断言"链路发生"以 8080 访问日志为准，内容断言保持宽松，避免过死。
7. `LGHJ_INTERNAL_API_TOKEN` 在测试期间为 `phase7-internal-token`；未配置（空）时双方均不校验，属原契约语义。

## 七、交付物清单

| 文件 | 说明 |
| --- | --- |
| `tests/API清单-api-inventory.md` | 57 项全量 API 契约清单（含坑点汇总） |
| `tests/conftest.py` + `tests/test_*.py`（7 个） | 68 条契约用例，随机用户 + 自清理，可重复执行 |
| `tests/文件清单-file-manifest.md` | tests 目录双语说明 |
| `tests/联调报告-integration-report.md` | 本报告 |
| `启动三服务-run-all-services.bat` / `停止三服务-stop-all-services.bat` | 一键启动/停止三服务（含 INTERNAL_TOKEN 环境变量） |
| `总说明-README.md`（根） | 补全三服务启动方式与各服务章节 |
