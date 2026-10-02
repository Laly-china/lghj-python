# API清单-api-inventory（前端 → Python 三服务 全量契约清单）

> 依据：前端源码 `lghj-web-dist.tar/lghj_web/src/api/`（auth.js / stock.js / trade.js / user.js /
> community.js / admin.js / agent.js 共 7 个模块）+ `vite.config.js` 代理 + `utils/request.js`
> 拦截器 + 各视图（*.vue）的字段消费点。用于 Phase 7 契约自测（pytest）的覆盖依据。

## 0. 路由与代理规则（vite.config.js，前端 baseURL=`/api`）

| 前端路径前缀 | 转发目标 | rewrite |
| --- | --- | --- |
| `/api/ml/**` | `http://localhost:8001` | 剥离 `/api/ml`（`/api/ml/minute/sh600519` → 8001 `/minute/sh600519`） |
| `/api/v1/**` | `http://localhost:8091` | 原样（8091 路由挂载在 `/api/v1/*`） |
| 其余 `/api/**` | `http://localhost:8080` | 原样 |

## 1. request.js 拦截器（三种响应体的前端适配）

- **主服务（8080）**：`Result{code, msg, data}`，成功码 `200`（数字）。
- **Agent 服务（8091）**：`Response{code, info, data}`，成功码 `"0000"`（字符串）。
- **预测服务（8001）**：**裸 JSON**——数组（分时）或 `{symbol, predictions}` 对象，拦截器
  特判 `Array.isArray(res)` / `res.symbol && Array.isArray(res.predictions)` 包装成 `{code:200,data}`。
- 401 → 前端强制登出；错误分支读 `res.msg || res.info`。
- 鉴权头名：`token`（axios `config.headers['token']`）。

## 2. auth.js（3 个接口，主服务 8080）

| # | 方法 路径 | 传参 | 响应契约（前端消费点） |
| --- | --- | --- | --- |
| 1 | POST `/api/login` | body `{username, password}` | `data:{token,id,username,userType,identityDesc,state}`；Login.vue 取 `token` 与 `userType===3` 跳管理端 |
| 2 | POST `/api/register` | body `{username, password, nickName?, email?, phone?}` | Result，data 可为 null |
| 3 | POST `/api/logout` | 无参 | Result（/api/logout 不在拦截范围） |

## 3. stock.js（9 个前端函数，8 个可测契约）

| # | 方法 路径 | 传参 | 响应契约（前端消费点） | 鉴权 |
| --- | --- | --- | --- | --- |
| 4 | GET `/api/user/stock/search` | query `keyword` | `data:[{id,symbol,name,industry,marketType}]`（Simulation/Watchlist/Prediction 取 `item.symbol` `item.name`） | 放行 |
| 5 | GET `/api/user/realtime/news` | query `symbol`, `recentN`(默认10) | `data:[{keyword,title,content,publishTime,source,url}]` | 放行 |
| 6 | GET `/api/ml/minute/{symbol}` | 路径 symbol | 8001 **裸数组** `[{time,price,volume,avg_price}]` 4 字段（Java 主服务 fetchFromPythonService 以 List 整体解析） | 无 |
| 7 | GET `/api/ml/predict/{symbol}` | 路径 symbol | 8001 **裸对象** `{symbol, predictions:[{date,price}]×30}`（Dashboard 读 `res.data.predictions[i].date/.price`） | 无 |
| 8 | GET `/api/user/stock/data` | query `symbol`, `period`(默认 D；D/W/M) | `data:[{date,open,close,low,high}]`（Dashboard/Market 按 date 排序画 K 线） | 放行 |
| 9 | GET `/api/user/prediction/{symbol}/get_excel` | 路径 symbol | **前端死接口**：原 Java 后端亦无该路由（已 grep 验证），导出预测 Excel 功能原系统未实现，不在复现与测试范围 | - |
| 10 | POST `/api/user/optional/add` | **query** `symbol` | Result（Redis Set + DB 双写） | token |
| 11 | POST `/api/user/optional/remove` | **query** `symbol` | Result | token |
| 12 | GET `/api/user/optional/list` | 无 | `data:[{stockId,symbol,name,price,changePercent,volume,followTime}]`（Watchlist.vue 消费 `symbol/name/currentPrice/changePercent/followTime`——`currentPrice` 为前端字段名差异，后端契约字段为 `price`，原 Java VO 即如此，忠实保留） | token |

## 4. user.js（2 个接口，主服务 8080）

| # | 方法 路径 | 传参 | 响应契约 | 鉴权 |
| --- | --- | --- | --- | --- |
| 13 | PUT `/api/user/follow/{id}/{isFollow}` | 路径 id, isFollow(true/false) | Result | token |
| 14 | GET `/api/user/follow/or/not/{id}` | 路径 id | `data: true/false` | token |

## 5. trade.js（8 个接口，主服务 8080）

| # | 方法 路径 | 传参 | 响应契约（前端消费点） | 鉴权 |
| --- | --- | --- | --- | --- |
| 15 | POST `/api/user/account/create` | 无 | `data:{id,userId,totalCash,availableCash,frozenCash,totalAsset,version,...}`（初始 20 万） | token |
| 16 | GET `/api/user/account/query_info` | 无 | 同上；无账户 → `code:500 msg:"账户不存在"`（Simulation.vue 消费 `totalAsset/availableCash/frozenCash`，**驼峰 totalAsset 为硬性字段**） | token |
| 17 | GET `/api/user/account/query_positions` | 无 | `data:[{id,userId,accountId,symbol,totalQuantity,frozenQuantity,availableQuantity,costPrice,profitLoss,version,...}]`（Simulation.vue 消费 `symbol/quantity/avgPrice/marketValue/profit`——后两者前端固有差异，后端契约字段 `costPrice/profitLoss` 照抄原 Java） | token |
| 18 | GET `/api/user/account/query_position` | query `symbol` | `data:{...持仓}` / `code:500 "持仓不存在"` | token |
| 19 | POST `/api/user/trade/order` | **query** `symbol, direction(1买/2卖), price, quantity(手)` | `data:{...trade_order 实体}`；买价≥现价 ≤4 秒内成交（状态 3） | token |
| 20 | POST `/api/user/trade/cancel` | **query** `orderId` | 成功 Result；失败 `code:500 msg:"撤销失败"` | token |
| 21 | GET `/api/user/trade/query_orders` | 无 | `data:[{id,orderNo,userId,symbol,direction,price,quantity,tradedQuantity,status,cancelTime,createTime,...}]`（status: 1待定 2部分完成 3已完成 4已撤销；Simulation.vue 消费 `id/createTime/symbol/direction/price/quantity/filledQuantity*/status`，TradeManage.vue 消费 `code/name/type/count*`——*为前端固有字段差异，后端照抄原 Java 实体） | token |
| 22 | GET `/api/user/trade/query_deals` | 无 | `data:[{id,dealNo,orderId,userId,symbol,dealDirection,price,quantity,createTime,...}]`（Simulation.vue 消费 `dealTime*`；TradeManage.vue 消费 `stockCode/stockName/dealPrice/dealCount/direction*`——后端契约字段为 `dealDirection/price/quantity`，照抄原 Java） | token |

## 6. community.js（13 个接口，主服务 8080）

| # | 方法 路径 | 传参 | 响应契约（前端消费点） | 鉴权 |
| --- | --- | --- | --- | --- |
| 23 | POST `/api/user/blog` | body **`{title, context}`**（community.js 显式把 content 改名为 **context** 再发送——坑点） | `data: 博客id` | token |
| 24 | PUT `/api/user/blog/like/{id}` | 路径 id | Result | token |
| 25 | GET `/api/user/blog/query/of/me` | query `current`(1), `size`(10) | `data: Page{records,total,...}`（Community.vue 兼容数组/records/list 三种） | token |
| 26 | GET `/api/user/blog/query/hot` | query `current`, `size` | 同上，按点赞热度排序 | 放行 |
| 27 | GET `/api/user/blog/query/{id}` | 路径 id | `data:{id,title,context(内容字段名),userId,name,icon,liked,isLike,createTime,...}`（Community.vue 消费 `content||context` 双兜底） | token |
| 28 | GET `/api/user/blog/query/of/user` | query `id`(必传), `current`, `size` | Page 结构 | 放行 |
| 29 | GET `/api/user/blog/query/of/follow` | query `current`, `size` | `data:[{...}]` Feed 流（Redis 收件箱 zrevrange + ORDER BY FIELD 保序） | token |
| 30 | DELETE `/api/user/blog/delete/{id}` | 路径 id | Result | token |
| 31 | PUT `/api/user/blog/update` | body `{id, title, ...}` | Result（原 BlogUpdateDTO 仅 id/title/images 生效，content 不落库，忠实保留） | token |
| 32 | POST `/api/user/blog/comments/add` | body `{blogId, userId?, content, parentId(0=一级)}` | Result | token |
| 33 | GET `/api/user/blog/comments/list` | query `blogId`(必传), `pageNum`(1), `pageSize`(10) | `data: PageResult{list,total,...}`，list 元素 `{id,blogId,parentId,content,liked,isLiked,user:{id,nickname,avatar},children:[...]}`（Community.vue 消费 `comment.content/user.nickname/user.avatar/children`） | 放行 |
| 34 | POST `/api/user/blog/comments/like/{commentId}` | 路径 commentId | Result | token |
| 35 | DELETE `/api/user/blog/comments/delete/{commentId}` | 路径 commentId | Result | token |

## 7. admin.js（12 个接口，主服务 8080，userType=3）

| # | 方法 路径 | 传参 | 响应契约（前端消费点） |
| --- | --- | --- | --- |
| 36 | GET `/api/admin/user` | query 分页条件（UserQueryDTO） | `data: PageResult{list,total}`（**UserManage.vue 唯一消费 `.list` 的管理端接口**；其余管理端分页为 Page{records,total}——两种分页体并存，坑点）；VO 无 id 字段，`sex/userType/status` 为中文枚举名 |
| 37 | POST `/api/admin/user/add` | body UserDTO | Result；用户名重复 → code:500 |
| 38 | DELETE `/api/admin/user/{id}` | 路径 id | Result（逻辑删除；**管理端禁删Admin**） |
| 39 | PUT `/api/admin/user/update` | body UserUpdateDTO | Result |
| 40 | POST `/api/admin/user/changeStatus/{id}` | **query** `status` | Result，`msg:"启用账号成功"/"禁用账号成功"` |
| 41 | GET `/api/admin/trade/order/page` | query `pageNum,pageSize,userId?,symbol?` | `data: Page{records,total,size,current,pages,...}`（TradeManage.vue 消费 records） |
| 42 | GET `/api/admin/trade/deal/page` | 同上 | Page 结构 |
| 43 | GET `/api/admin/blog/page` | query 分页 | Page{records,total,...} |
| 44 | DELETE `/api/admin/blog/{id}` | 路径 id | Result |
| 45 | GET `/api/admin/blog/comments/page` | query 分页, `blogId?` | Page 结构 |
| 46 | DELETE `/api/admin/blog/comments/{id}` | 路径 id | Result（不级联） |
| 47 | GET `/api/admin/stock/page` | query `pageNum,pageSize,keyword?` | Page{records,total,...}（StockManage.vue 消费 `tsCode/symbol/name/area/industry/market/listDate`） |
| 48 | PUT `/api/admin/stock/update` | body 股票字段（含 symbol） | Result，成功文案在 msg |
| 49 | POST `/api/admin/stock/import` | 无 | Result（**拦截器放行，无需 token**） |
| 50 | POST `/api/admin/stock/sync-es` | 无 | Result（ES 简化占位契约） |
| 51 | POST `/api/admin/stock/batch-update` | 无 | Result |

（另有 GET `/api/admin/user/{id}`、GET `/api/admin/blog/{id}` 详情接口，前端未直接调用，一并纳入鉴权/契约抽测。）

## 8. agent.js（3 个前端函数 + 1 个后端流式接口，Agent 服务 8091）

| # | 方法 路径 | 传参 | 响应契约（前端消费点） |
| --- | --- | --- | --- |
| 52 | GET `/api/v1/query_ai_agent_config_list` | 无 | `Response{code:"0000", info:"成功", data:[{agentId, agentName, agentDesc}]}`（Prediction.vue 取 `res.data` 数组、`agent.agentId`） |
| 53 | POST `/api/v1/create_session` | body `{agentId, userId}`（另有 GET 同名接口） | `data:{sessionId}`（Prediction.vue 取 `res.data?.sessionId`；同 userId 幂等复用） |
| 54 | POST `/api/v1/chat` | body `{agentId, userId, sessionId, message}` | `data:{content}`（各事件文本按 `\n` 连接；Prediction.vue 取 `res.data?.content`） |
| 55 | POST `/api/v1/chat_stream` | 同 chat | HTTP 200 `text/plain` chunked 文本流（无 `data:` SSE 前缀；前端未接，属后端契约，抽测流非空） |

错误码：`E0001` 智能体ID不存在；`0001` 未知失败；`0002` 非法参数。

## 9. 内部 API（8080 `/api/internal/*`，供 8091 调用，前端不直接调用）

| # | 方法 路径 | 传参 | 响应契约 |
| --- | --- | --- | --- |
| 56 | GET `/api/internal/market/realtime` | query `code`(必传), `market?`(缺省按 5/6/9→sh 否则 sz), `recentNewsSize?`(截断[0,20]), `includeMinute?` | 裸 dict `{market,code,queryTime,quote,minuteData,news}`；鉴权 `X-Internal-Token`（LGHJ_INTERNAL_API_TOKEN 非空必须匹配，缺失/错误 → 401） |
| 57 | GET `/api/internal/sim-trade/profile` | query `userId`(必传) | 裸 dict 画像（含 behaviorTags，无交易用户=[NO_TRADE_RECORD]）；鉴权同上 |

## 10. 跨服务链路（Phase 7 端到端验证点）

| 链路 | 验证内容 |
| --- | --- |
| 8001 → 8080 | GET `/api/user/realtime/minute?symbol=sh600519`（8080 RealTimeStockService 内部 HTTP 调 8001 `/minute/sh600519`）应取到分时数组 |
| 8091 → 8080 | 8091 chat 问"我的持仓/行情"，agent 工具经 X-Internal-Token 调 8080 `/api/internal/sim-trade/profile` 与 `/api/internal/market/realtime`，SSE/文本流非空且内容含工具数据痕迹 |
| vite → 8001/8091 | `/api/ml/*` 与 `/api/v1/*` 代理剥离规则已按第 0 节直测对应目标服务 |

## 11. 前端消费坑点汇总（测试重点断言）

1. 博客内容字段名是 **`context`**（发布 body 与详情/列表响应均为 context，前端有 `content||context` 双兜底但发布侧必须收 context）。
2. 账户 **`totalAsset/availableCash/frozenCash`** 驼峰（Simulation.vue 直接渲染）。
3. query string 传参：下单 symbol/direction/price/quantity、撤单 orderId、自选股 add/remove symbol、changeStatus status。
4. 管理端分页体并存：`/admin/user` 为 `{list,total}`（PageResult），其余管理端 page 为 Page `{records,total,...}`。
5. 三种响应体并存：8080 `Result{code:200,msg,data}` / 8091 `Response{code:"0000",info,data}` / 8001 裸 JSON（数组或 `{symbol,predictions}`）。
6. `/api/user/optional/list` 契约字段为 `price`，前端 Watchlist.vue 消费 `currentPrice/followTime`（原 Java VO 即 `price`，属前端固有差异，忠实保留后端契约）。
7. `get_excel`（`/api/user/prediction/{symbol}/get_excel`）为前端死接口，原 Java 亦无此路由，不复现（记录为已知差异）。
