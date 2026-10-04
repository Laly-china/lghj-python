# 文件清单-file-manifest（tests/ 联调自测目录）

Phase 7：三服务联调 + 全量 API 契约自测。**pytest 测试文件按工具收集约定保留英文
`test_*.py` 命名**，逐个中文说明如下。

| 文件 | 中文职责说明 |
| --- | --- |
| `conftest.py` | pytest 公共夹具：三服务地址常量（MAIN/AGENT/PRED）、随机用户工厂（注册+登录，teardown 经管理端逻辑删除自清理）、admin 会话夹具、trader_user（已成交用户）夹具、MySQL 只读连接、Result/Response 断言辅助、8080 访问日志增量读取（端到端工具链佐证） |
| `API清单-api-inventory.md` | 前端 7 个 api 模块 + vite 代理梳理出的全量 API 契约清单（路径/方法/传参/响应字段消费点/三种响应体/坑点汇总），pytest 覆盖依据 |
| `test_auth.py` | auth.js 契约：注册/登录/登出、错误密码、不存在用户、重复注册、可选字段注册；拦截器鉴权语义：无 token 401、伪造 token 401、普通用户访问管理端 403(20012)、放行清单逐条匿名可访问、/api/internal 不走 JWT |
| `test_stock.py` | stock.js 契约：600519 前缀搜索（StockDoc 五字段）、"银行"模糊搜索、实时行情八字段、K线 D/W/M 三周期（date/open/close/high/low）、新闻 recentN 截断与 StockNewsVO 字段、自选股 add/list/remove 全流程（query string 传参 + StockFollowVO 字段 + followTime） |
| `test_trade.py` | trade.js 契约（交易全链路）：建户 20 万字段、query_info 的 totalAsset/availableCash/frozenCash 驼峰、无账户 code=500、买价≥现价立即成交（≤4 秒量级，成交记录 dealNo/dealDirection）、持仓 totalQuantity/costPrice/profitLoss、卖出清仓回款、低价单撤单（状态 4 + cancelTime + 冻结解冻）、撤销不存在/他人订单 code=500"撤销失败"、资金不足 code=50001、一买一卖总资产≈20 万对账、委托/成交列表字段契约 |
| `test_community.py` | community.js + user.js 契约：发布博客 body 用 **context** 字段名、query/of/me 列表、详情补作者昵称、query/of/user 与 query/hot 放行、博客点赞 toggle（liked/isLike）、一级/二级评论树（PageResult{list,total} + user.nickname + children）、评论点赞（isLiked/liked）、删除一级评论、关注/取关/or-not、Feed 流 PageResult + 时间倒序保序、编辑标题、删除他人博客 30003、已删详情 30002 |
| `test_admin.py` | admin.js 契约：/admin/user 为 **PageResult{list,total}**（唯一 .list 消费点）、UserVO 无 id 字段 + 中文枚举、用户增改启禁删全流程（changeStatus 文案"启用/禁用账号成功"）、重复用户名 500、trade/order/page 与 deal/page 为 **Page{records,total,size,current,pages}** + userId 过滤、博客/评论/股票分页 Page 结构、股票按 symbol 幂等更新、sync-es 文案"同步完成"、init-es 放行且文案含 5458 条 |
| `test_agent.py` | agent.js + 内部 API 契约：config_list（code="0000" + agentId/agentName/agentDesc）、create_session GET/POST 双契约（**每次新建会话**——历史落库后放弃原 Java 同 userId 复用语义，否则「新建对话」折进同一历史行）、坏 agentId E0001、chat LLM 真调 content 非空、chat_stream 流式 text/plain 非空、**端到端工具链**（chat 问"我的交易画像"→ 8080 日志出现 /api/internal/sim-trade/profile）、X-Internal-Token 正确/错误/缺失语义、market 推断（000001→sz）、code 缺失/空白语义、内部交易画像（NO_TRADE_RECORD）；**可视化扩展接口**（原 Java 无）：agent_team 团队结构（队长+6 专家含职能描述+2 本地工具名）、trace 事件结构（run_start 边界/agent_text/公共字段/合法 type）、trace 记录工具调用（querySimTradeProfile 入参 userId+耗时；transfer 出现时结构合法但不强制——真实 LLM 可能由 Supervisor 直接调工具）；**历史/知识库/专家对话扩展接口**（原 Java 无）：QuantTechnicalAgent 独立建会话+chat 后 history_list/history_messages 落库校验+删除清理、知识库 kb_upload/kb_list/kb_doc 全流程（无 LLM） |
| `test_ml.py` | 预测服务（8001）+ 跨服务链路：/minute 裸数组恰 4 字段（time/price/volume/avg_price）、/predict 30 项 {date,price} 且日期升序、裸 6 位代码兼容、非法 symbol 400 invalid_symbol、**8080 /api/user/realtime/minute 经 8001 取数**（结构一致）、上证指数 sh000001 分时链路 |
| `联调报告-integration-report.md` | Phase 7 交付报告：API 覆盖率、通过率、发现并修复的 bug 清单、端到端链路验证结论、遗留问题 |
| `run-8080.log` / `run-8091.log` / `run-8001.log` | 三服务运行日志（测试期间采集，端到端断言读取 8080 日志增量） |

## 运行方式

```bash
# 先按《总说明-README.md》启动三服务（8080/8091/8001），
# 且 8080 与 8091 需带 LGHJ_INTERNAL_API_TOKEN=phase7-internal-token 环境变量
cd lghj-python
"..\env\venv-虚拟环境\Scripts\python.exe" -m pytest tests -v --tb=short
```

可重复执行：随机用户名后缀 + 测试数据自清理（用户逻辑删除、博客/评论/自选股经 API 删除）。
