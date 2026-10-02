# lghj-server 文件清单-file-manifest

主服务（FastAPI，端口 8080）。分层：controller（路由）→ service（业务）→ mapper（数据访问）
→ pojo（entity/dto/vo）。每个模块顶部 docstring 标注了对应复现的原 Java 类（相对路径
`feng-lghj/lghj-server/src/main/java/com/lghj/...`）。

## 命名规则说明

- 下方全部英文文件/目录均为 **Python import 机制必需**（包/模块名不可用中文）；
- 根目录、scripts/ 下不被 import 的文件使用 中文-english 双语命名。

## 根目录（lghj-server/）

| 文件 | 职责 |
| ---- | ---- |
| `文件清单-file-manifest.md` | 本清单：全部文件的中英文命名对照与职责说明 |
| `scripts/股票导入-import-stocks.py` | 独立运行的 A 股 Excel 导入脚本（对应原 POST /api/admin/stock/import + StockExcelListener；自带 sys.path 初始化，不作为 Python 包） |
| `scripts/测试脚本-测试订单簿-test-order-book.py` | 任务B 引擎级自测脚本：冷热分层订单簿的冷入簿/热溢出降级（60 热 + 50 冷精确断言）/冷晋升/撮合弹出全链验证（独立运行，不作为 Python 包） |

## app/ 应用包

| 英文文件/目录 | 中文职责说明（对应原 Java） |
| ---- | ---- |
| `app/__init__.py` | 应用包声明（对应 feng-lghj/lghj-server 模块） |
| `app/main.py` | **入口**：FastAPI 实例、路由自动发现（递归导入 controller/ 收集模块级 router）、拦截器与全局异常注册、uvicorn 启动入口 `app.main:app` 127.0.0.1:8080（对应 LghjServerApplication + WebMvcConfiguration）。**任务B 最小挂钩**：startup 钩子在 Redis 预热后调用 `app/task` 包的 start()（订单恢复 + 3 秒行情撮合调度，失败不阻断启动），shutdown 钩子调用 stop()；路由自动发现机制未改动 |
| `app/config.py` | 配置：MySQL(lghj/root@127.0.0.1:3306)、Redis(db8)、JWT(secret=itfeng, TTL=7200000000000ms, 头名 token)、外部 URL（对应 application-dev.yml + JwtProperties） |
| `app/database.py` | SQLAlchemy 2.0 engine/SessionLocal/get_db 依赖与 ORM 基类 Base（对应 MyBatisConfiguration + 数据源配置） |
| `app/interceptor.py` | JWT 登录校验中间件：/api/admin/** 与 /api/user/** 两组拦截，放行清单逐条照抄 excludePathPatterns；401/403 语义照抄（对应 WebMvcConfiguration + JwtTokenUserInterceptor + JwtTokenAdminInterceptor） |

## app/common/ 公共组件

| 英文文件 | 中文职责说明（对应原 Java） |
| ---- | ---- |
| `__init__.py` | 包声明 |
| `constants.py` | 全局常量：Redis 键前缀、外部 URL、状态/密码常量、缓存 TTL=24h 等（对应 constant/RedisConstant、UrlConstant、StockConstant、StatusConstant、PasswordConstant、JwtClaimsConstant） |
| `community_constants.py` | **社区模块常量（任务C）**：博客点赞 ZSet 键 `blog:liked:`、Feed 收件箱键 `feed:`、关注 Set 键 `follows:`、评论点赞 Set 键 `blog:comment:liked:`、点赞状态 LIKED/UNLIKED（对应 constant/RedisConstant 社区部分 + constant/LikeStatusConstant，键名逐字照抄；因 constants.py 属任务A 文件不可改，单列于此） |
| `mp_page.py` | **MyBatis-Plus Page 分页 JSON 序列化等价实现（任务C）**：管理端分页 `{records,total,size,current,pages,orders,searchCount,optimizeCountSql,countId,maxLimit,hitCount}`（对应 Page 3.5.7 经 Jackson 输出；与 PageResult{list,total} 为两种不同响应结构，不可混用） |
| `result.py` | 统一响应体 `Result{code,msg,data}` 与 `ErrorEnum` 全量错误码（对应 pojo/dto/Result.java + enums/ErrorEnum.java，含原文件重复码值的忠实保留） |
| `exception.py` | `BusinessException` 与全局异常处理器（对应 exception/BusinessException + handler/GlobalExceptionHandler） |
| `context.py` | 当前登录用户上下文（contextvars 实现，对应 context/BaseContext 的 ThreadLocal） |

## app/utils/ 工具

| 英文文件 | 中文职责说明（对应原 Java） |
| ---- | ---- |
| `__init__.py` | 包声明 |
| `jwt_util.py` | JWT HS256 签发/解析（对应 utils/JwtUtil.java） |
| `redis_client.py` | Redis 客户端（db8）与缓存读写封装（对应 StringRedisTemplate 用法，异常降级语义对齐） |
| `redis_id_worker.py` | Redis 全局唯一 ID 生成器：时间戳<<32 \| INCR 序列号，键 `icr:{前缀}:{yyyy:MM:dd}`（对应 utils/RedisIdWorker.java） |
| `lock_util.py` | Redis 分布式锁（SET NX PX + Lua 校验释放；对应 utils/RedissonLockUtil.java 的 Redisson 语义） |
| `http_client.py` | httpx 共享异步客户端与请求头封装（对应 hutool HttpUtil / RestTemplate 调用） |
| `hybrid_order_book.py` | **混合订单簿（冷热分层撮合引擎）**：热数据=内存优先队列（买单价高→低、卖单价低→高，容量 100），冷数据=Redis ZSet `orderbook:{symbol}:buy/:sell`（member=订单JSON/score=价格）；现价 ±5%（0.05）为热区间，热满 100 溢出降级 50 条，价格变化时冷订单按新区间晋升回热队列；撮合判定买价>=现价/卖价<=现价、按现价全额成交（对应 utils/HybridOrderBook.java；修赁原实现"撤单时 DB 回读价格标度变化导致 ZSet 成员无法命中"的缺陷，zrem 未命中时按订单 ID 扫描清除） |
| `order_queue_manager.py` | **每 symbol 单线程撮合队列**：每股票一个 asyncio.Queue + 独立消费者协程（同一股票串行、跨股票并行），消费者经 asyncio.to_thread 执行同步撮合动作不阻塞事件循环；add_order 线程安全（事件循环线程直接入队/工作线程经 call_soon_threadsafe 投递），shutdown 对应原 @PreDestroy（对应 utils/OrderQueueManager.java） |

## app/pojo/entity/ 实体（init.sql 全部 15 张表）

| 英文文件 | 中文职责说明 |
| ---- | ---- |
| `__init__.py` | 实体包统一导出（后续任务只 import 不重建） |
| `base.py` | 序列化混入：JSON 驼峰字段名 + `yyyy-MM-dd HH:mm` 时间格式（对应 JacksonObjectMapper + map-underscore-to-camel-case） |
| `user.py` | 用户表 user（对应 entity/User.java） |
| `role.py` | 角色表 role（对应 entity/Role.java） |
| `permissions.py` | 权限表 permissions（对应 entity/Permissions.java） |
| `user_role.py` | 用户-角色关联表 user_role（对应 entity/UserRole.java） |
| `role_permission.py` | 角色-权限关联表 role_permission（**原 Java 无实体，按 init.sql 补齐**） |
| `blog.py` | 博客表 blog（对应 entity/Blog.java，仅建模） |
| `blog_comments.py` | 博客评论表 blog_comments（对应 entity/BlogComments.java，仅建模） |
| `follow.py` | 关注关联表 follow（对应 entity/Follow.java，仅建模） |
| `stock_basic.py` | A股基础信息表 stock_basic（对应 entity/StockBasic.java） |
| `trade_order.py` | 委托单表 trade_order（对应 entity/TradeOrder.java，仅建模） |
| `trade_deal.py` | 成交记录表 trade_deal（对应 entity/TradeDeal.java，仅建模） |
| `sim_account.py` | 模拟账户表 sim_account（对应 entity/SimAccount.java，含乐观锁 version） |
| `user_position.py` | 用户持仓表 user_position（对应 entity/UserPosition.java，含乐观锁 version） |
| `account_flow.py` | 资金流水表 account_flow（对应 entity/AccountFlow.java，仅建模） |
| `user_stock_follow.py` | 用户自选股表 user_stock_follow（对应 entity/UserStockFollow.java，唯一键 user_id+stock_id） |

## app/pojo/dto/ 请求对象

| 英文文件 | 中文职责说明 |
| ---- | ---- |
| `__init__.py` | DTO 包统一导出 |
| `login_dto.py` | 登录请求体 {username,password}（对应 dto/LoginDTO.java） |
| `register_dto.py` | 注册请求体，@NotBlank/@Pattern 校验照抄（对应 dto/RegisterDTO.java） |
| `page_result.py` | 分页封装 {total,totalPage,pageNum,pageSize,list}（对应 dto/PageResult.java，Phase 1 未使用，供后续任务复用） |
| `stock_excel.py` | Excel 列映射（索引 0/1/3/4/5/6/7/8/9，索引 2 跳过；对应 dto/StockExcel.java） |
| `blog_dtos.py` | **博客模块 DTO 集合（任务C）**：BlogCommentAddDTO（blogId/parentId/content，@NotBlank 照抄）、BlogUpdateDTO（id/title/images，对应 dto/BlogCommentAddDTO + BlogCommentQueryDTO + BlogUpdateDTO；评论查询参数由控制器 Query 直接绑定） |
| `user_manage_dtos.py` | **管理端用户 DTO 集合（任务C）**：UserDTO（@NotBlank/@NotNull 照抄）、UserQueryDTO（分页条件查询参数）、UserUpdateDTO（对应 dto/UserDTO + UserQueryDTO + UserUpdateDTO） |

## app/pojo/vo/ 响应对象

| 英文文件 | 中文职责说明 |
| ---- | ---- |
| `__init__.py` | VO 包统一导出 |
| `login_vo.py` | 登录返回 {token,id,username,userType,identityDesc,state}（对应 vo/LoginVO.java） |
| `stock_doc.py` | 搜索结果 {id,symbol,name,industry,marketType}（对应 doc/StockDoc.java，原 ES 文档，契约不变） |
| `stock_news_vo.py` | 新闻条目 {keyword,title,content,publishTime,source,url}（对应 vo/StockNewsVO.java） |
| `stock_follow_vo.py` | 自选股条目 {stockId,symbol,name,price,changePercent,volume}（对应 vo/StockFollowVO.java） |
| `blog_vos.py` | **博客评论 VO 集合（任务C）**：BlogCommentVO（含 user/isLiked/children 二级树）、UserBlogCommentsMessageDTO（id/nickname/avatar；**原 Java hutool 拷贝属性名不匹配，nickname/avatar 恒为 null，忠实保留**）（对应 vo/BlogCommentVO.java + dto/UserBlogCommentsMessageDTO.java） |
| `user_vo.py` | **管理端用户 VO（任务C）**：{username,password,email,phone,sex,userType,status,createTime,updateTime,createUser,updateUser,isDeleted}；sex/userType/status 为枚举转中文名，**原 VO 无 id 字段**，createUser/updateUser 为字符串（对应 vo/UserVO.java） |

## app/mapper/ 数据访问层

| 英文文件 | 中文职责说明（对应原 Java mapper 包） |
| ---- | ---- |
| `__init__.py` | 包声明 |
| `user_mapper.py` | 用户表查询/插入（对应 mapper/UserMapper.java） |
| `user_manage_mapper.py` | **管理端用户表数据访问（任务C）**：分页条件查询（like/eq/时间区间/update_time 倒序）、按主键查/批量查、非空字段更新、逻辑删除（对应 UserServiceImpl 中的 selectPage/selectById/updateById/deleteById 语义 + 全局 logic-delete-field: isDeleted） |
| `user_role_mapper.py` | **用户-角色关联表数据访问（任务C）**：插入/按用户查/更新 role_id/按用户逻辑删除（对应 UserRoleServiceImpl 的 save/getOne/updateById/remove 语义） |
| `blog_mapper.py` | **博客表数据访问（任务C）**：插入/按主键/按用户分页/热度分页/无条件分页/计数/`ORDER BY FIELD(id,...)` 保序批量查/点赞数原子增减/非空更新/逻辑删除（对应 mapper/BlogMapper.java + BlogServiceImpl 的 MP 用法；全局逻辑删除语义一致） |
| `blog_comments_mapper.py` | **博客评论表数据访问（任务C）**：插入/按主键/一级评论分页/二级评论批量查/按父评论查/点赞数赋值更新/批量逻辑删除/管理端分页（对应 BlogCommentsServiceImpl 的 MP 用法） |
| `follow_mapper.py` | **关注关联表数据访问（任务C）**：插入/取关逻辑删除/user+被关注计数/按被关注用户查粉丝列表（对应 mapper/FollowMapper.java + FollowServiceImpl 的 MP 用法） |
| `stock_basic_mapper.py` | 股票表查询：按代码/批量/LIKE 搜索/批量插入/计数（对应 mapper/StockBasicMapper.java；search_like 为原 ES boolQuery 的 MySQL LIKE 替代） |
| `stock_manage_mapper.py` | **管理端股票表数据访问（任务C）**：keyword 分页（symbol/name LIKE 或 + create_time 倒序）/按代码非空更新（对应 StockServiceImpl.pageQuery/updateByCode 语义） |
| `user_stock_follow_mapper.py` | 自选股表：计数/按用户查询/插入/删除（对应 mapper/UserStockFollowMapper.java） |
| `trade_order_mapper.py` | 委托单表：插入/按主键查/按主键更新（MP NOT_NULL 字段策略语义）/用户订单列表/未完成订单（状态 1、2）/管理端分页（对应 mapper/TradeOrderMapper.java + TradeServiceImpl、TradeManageController、OrderRecoveryTask 内联查询） |
| `trade_deal_mapper.py` | 成交记录表：插入/用户成交列表/管理端分页（对应 mapper/TradeDealMapper.java + TradeServiceImpl 内联查询） |
| `sim_account_mapper.py` | 模拟账户表：按用户查询/插入（对应 mapper/SimAccountMapper.java） |
| `user_position_mapper.py` | 持仓表：按用户/按用户+代码查询（对应 mapper/UserPositionMapper.java） |
| `sim_trade_profile_mapper.py` | **交易画像只读数据访问（任务C）**：按用户查订单/成交列表（is_deleted=0 + create_time 倒序，对应 TradeServiceImpl.getUserOrders/getUserDeals 的查询语义；仅复现这两处只读查询，交易写操作归任务B） |

## app/service/ 业务层

| 英文文件 | 中文职责说明（对应原 Java service/impl 包） |
| ---- | ---- |
| `__init__.py` | 包声明 |
| `login_service.py` | 登录（账号/明文密码/状态校验）与注册（对应 LoginServiceImpl；**明文密码为原系统行为**） |
| `account_service.py` | 模拟账户：创建（初始 20 万、version=1）/查询/持仓（对应 AccountServiceImpl） |
| `stock_search_service.py` | 股票搜索（MySQL LIKE 替代 ES，返回 StockDoc，对应 StockSearchServiceImpl.search） |
| `real_time_stock_service.py` | 实时行情（腾讯 ~ 分割，字段 1/2/3/4/5/6/31/32）、历史K线（新浪 scale=240/1200/7200 + 腾讯 day/week/month 降级，Redis 24h）、东方财富新闻 JSONP、分时（调 8001 预测服务 + 锁防击穿）（对应 RealTimeStockServiceImpl 全部方法） |
| `stock_service.py` | Excel 导入：列解析/代码归一化/市场类型判定/日期解析/100 条分批入库（对应 StockServiceImpl.importStockBasic + listener/StockExcelListener） |
| `user_stock_follow_service.py` | 自选股增删查：Redis Set `user:stock:follow:{userId}` 与 DB 双写、列表带行情（对应 UserStockFollowServiceImpl） |
| `blog_service.py` | **博客业务（任务C Phase 3+4）**：发布（粉丝 feed:ZSet 推送收件箱，score=毫秒时间戳）、点赞（Redis ZSet blog:liked:{id} 成员切换 + liked 原子增减）、我的/指定用户/热度分页、详情（补作者昵称头像 + isLike，游客为 null）、Feed 流收件箱分页（zrevrange + ORDER BY FIELD 保序）、删除（逻辑删除 + 清理点赞 ZSet 与全部 feed:*）、编辑（仅 title/images + update_time）、管理端 page/删除/详情（对应 BlogServiceImpl 全部方法 + admin/BlogManageController 对泛型方法的调用） |
| `blog_comments_service.py` | **博客评论业务（任务C Phase 3+4）**：新增（二级校验父评论存在/同博客/状态正常）、列表（一级分页倒序 + 批量二级正序 + 树形 VO + 用户信息 + isLiked）、点赞（Redis Set blog:comment:liked:{id} 成员切换 + liked 绝对值回写，照抄原非原子语义）、删除（逻辑删除 + 一级级联删二级 + 清点赞缓存）、管理端 page（可选 blogId）/删除不级联（对应 BlogCommentsServiceImpl 全部方法） |
| `follow_service.py` | **关注业务（任务C Phase 3）**：关注/取关（DB 与 Redis Set follows:{userId} 双写，无重复关注校验照抄）、是否关注（count 查询，对应 FollowServiceImpl） |
| `user_manage_service.py` | **管理端用户业务（任务C Phase 4）**：分页条件查询（PageResult{list,total} 结构 + 枚举名转换 VO，无 id 字段）、新增（用户名查重抛 RuntimeException→SYSTEM_ERROR、userType→role 映射 1/2/3 与管理员角色 3-6 校验、事务回滚）、删除（用户与 user_role 先后逻辑删除，对齐原无事务自动提交）、按 id 查、修改（非空字段 + 角色联动）、启用禁用（对应 UserServiceImpl + UserTypeRoleMapEnum + Sex2Num/Status2Num/UserType2Num） |
| `stock_manage_service.py` | **管理端股票业务（任务C Phase 4）**：keyword 分页（Page 结构）、按代码非空更新、Excel 批量更新（复用 stock_service 的 read_excel_rows/resolve_excel_path，对应 StockUpdateListener 每 100 条一批逐条 update） |
| `sim_trade_profile_service.py` | **模拟交易用户画像业务（任务C Phase 4 内部 API）**：聚合账户/持仓/订单/成交（各限最近 30 条，统计全量）→ 统计汇总（买卖金额、持仓成本、重仓占比 4 位小数 HALF_UP、活跃品种、各品种成交次数）+ **6 个行为标签**：NO_TRADE_RECORD（无交易）/CONCENTRATED_POSITION（单持仓或重仓占比≥0.60）/HIGH_ORDER_FREQUENCY（订单≥20）/FREQUENT_CANCEL（撤单 status=4 ≥5）/BUY_SIDE_BIAS（买入>卖出×2 且非空）/DIVERSIFIED_TRADING（成交去重品种≥5）；数据只读直查 trade_order/trade_deal/sim_account/user_position，不依赖任务B 代码（对应 SimTradeProfileServiceImpl 全部算法，逐条照抄） |
| `trade/`（包） | **模拟交易业务包（任务B Phase 2）**，文件拆分对应原 service/trade 包与 TradeServiceImpl：见下列各行 |
| `trade/trade_direction_strategy.py` | 交易方向策略接口：reserve 预冻结 / release 释放 / canExecute 可成交判定 / validateBeforeDeal 成交前校验 / settle 结算（对应 service/trade/TradeDirectionStrategy.java） |
| `trade/buy_trade_direction_strategy.py` | 买入策略：下单冻结资金（价×手数×100，可用不足抛 50001）、撤单解冻、买价>=现价成交、结算=加权平均成本+退差价（frozen-actual 差价退回可用）（对应 service/trade/BuyTradeDirectionStrategy.java） |
| `trade/sell_trade_direction_strategy.py` | 卖出策略：下单冻结持仓（可用不足抛 50002）、撤单解冻、卖价<=现价成交、结算=回款+扣减持仓、清仓逻辑删除（对应 service/trade/SellTradeDirectionStrategy.java） |
| `trade/trade_direction_router.py` | 方向路由：1→买、2→卖，未支持方向抛异常（对应 service/trade/TradeDirectionRouter.java） |
| `trade/trade_deal_executor.py` | 成交执行器：成交前校验→插入 trade_deal（DEAL+UUID前16位）→累计已成交/状态 3 或 2（全成时移出订单簿）→结算（对应 service/trade/TradeDealExecutor.java） |
| `trade/trade_account_operator.py` | 交易账户操作：账户/持仓读取、**乐观锁更新（UPDATE ... WHERE version=? AND is_deleted=0，检查影响行数，0 行抛 50004/50003）**、持仓逻辑删除、orderAmount=价格×手数×100（对应 service/trade/TradeAccountOperator.java；getAccount 改按 user_id 列查询，见报告偏差说明） |
| `trade/trade_service.py` | 交易核心服务：createOrder（冻结→落库→入撮合队列）、processOrder 撮合回调（trade:lock:{userId}:{symbol} 分布式锁 wait5s/lease30s→拉现价→可成交则执行否则挂订单簿）、cancelOrder（校验归属/状态→锁内 status=4+cancelTime→移出订单簿→release 退冻结）、订单/成交查询（对应 ITradeService + TradeServiceImpl；模块底部完成队列/订单簿处理器装配，对应 @PostConstruct init） |

## app/controller/ 路由层（main.py 自动发现，新增文件无需改 main.py）

| 英文文件 | 中文职责说明（对应原 Java controller 包） |
| ---- | ---- |
| `__init__.py` | 包声明（自动发现根） |
| `notify/__init__.py` | notify 分组包声明 |
| `notify/login_controller.py` | POST /api/login、/api/register、/api/logout（对应 notify/LoginController.java；签发 JWT 用 admin 配置，照抄原逻辑） |
| `user/__init__.py` | user 分组包声明 |
| `user/account_controller.py` | POST /api/user/account/create；GET query_info/query_positions/query_position（对应 user/AccountController.java） |
| `user/stock_search_controller.py` | GET /api/user/stock/search（LIKE 搜索）、/api/user/stock/data（K线，period 默认 D）（对应 user/StockSearchController.java） |
| `user/real_time_stock_controller.py` | GET /api/user/realtime/quote、/realtime/news（recentN 默认 10）、/realtime/minute（对应 user/RealTimeStockController.java） |
| `user/optional_stock_controller.py` | POST /api/user/optional/add、/optional/remove（symbol 走 query string）、GET /optional/list（对应 user/OptionalStockController.java） |
| `user/blog.py` | **讨论区博客路由（任务C Phase 3）**：POST /api/user/blog 发布、PUT /like/{id} 点赞、GET /query/of/me、/query/hot（放行）、/query/of/user（放行，id 必传）、/query/of/follow（Feed 流）、/query/{id}、DELETE /delete/{id}、PUT /update；路由声明顺序保证字面路径先于 /query/{id} 匹配（对应 user/BlogController.java） |
| `user/comments.py` | **博客评论区路由（任务C Phase 3）**：POST /api/user/blog/comments/add、GET /list（放行，blogId 必传/pageNum=1/pageSize=10）、POST /like/{commentId}、DELETE /delete/{commentId}（对应 user/BlogCommentsController.java） |
| `user/follow.py` | **关注路由（任务C Phase 3）**：PUT /api/user/follow/{id}/{isFollow}、GET /or/not/{id}（对应 user/FollowController.java） |
| `user/trade.py` | **用户交易路由（任务B）**：POST /api/user/trade/order 下单（query 参数 symbol/direction/price/quantity，direction 1买2卖，quantity 单位手）、POST /api/user/trade/cancel 撤单（query 参数 orderId，失败 code=500 "撤销失败"）、GET /api/user/trade/query_orders 委托单列表、GET /api/user/trade/query_deals 成交列表（对应 user/TradeController.java） |
| `admin/__init__.py` | admin 分组包声明 |
| `admin/stock_controller.py` | POST /api/admin/stock/import（Excel 导入，拦截器放行无需 token；对应 admin/StockController.java 的 importData，其余管理端接口不在 Phase 1 范围） |
| `admin/user.py` | **管理端用户管理路由（任务C Phase 4）**：GET /api/admin/user 分页条件查询（**PageResult{list,total} 结构**）、POST /add、DELETE /{id}、GET /{id}、PUT /update、POST /changeStatus/{id}?status=（msg=启用/禁用账号成功）（对应 admin/UserManageController.java） |
| `admin/blog.py` | **管理端博客管理路由（任务C Phase 4）**：GET /api/admin/blog/page（Page{records,total} 结构）、DELETE /{id}（逻辑删除）、GET /{id} 详情（对应 admin/BlogManageController.java） |
| `admin/comments.py` | **管理端评论管理路由（任务C Phase 4）**：GET /api/admin/blog/comments/page（可选 blogId，Page 结构，create_time 倒序）、DELETE /{id}（逻辑删除不级联）（对应 admin/BlogCommentsManageController.java） |
| `admin/stock.py` | **管理端股票路由（任务C Phase 4）**：POST /api/admin/stock/sync-es 与 /init-es（**ES 简化占位**：本工程搜索直接查 MySQL，不建索引仅保留契约路径与文案；init-es 条数取 MySQL 现有行数，init-es 拦截器放行）、GET /page（keyword 过滤，Page 结构）、PUT /update（按 symbol 更新，成功文案在 msg）、POST /batch-update（Excel 批量更新）（对应 admin/StockController.java 除 import 外的其余接口） |
| `internal/__init__.py` | **internal 分组包声明（任务C Phase 4）**：对应原 controller/internal 包 |
| `internal/market_realtime.py` | **内部行情聚合路由（任务C Phase 4，供 AI Agent 8091 调用）**：GET /api/internal/market/realtime?code&market&recentNewsSize&includeMinute，返回 {market,code,queryTime,quote,minuteData,news}（字段顺序照原 MarketRealtimeData 声明）；market 缺省按代码 5/6/9→sh 否则 sz 推断；recentNewsSize 截断 [0,20]；鉴权 X-Internal-Token（LGHJ_INTERNAL_API_TOKEN 环境变量，默认空=不校验，配置非空必须匹配，与 Agent 客户端 http_ports.py 严格对齐）；**不走 JWT 拦截器**（原 WebMvcConfiguration 仅挂 admin/user 两组，internal 由控制器自行校验）；code 参数缺失→SYSTEM_ERROR、空白→"stock code required"（对应 internal/MarketRealtimeController.java） |
| `internal/sim_trade_profile.py` | **内部交易画像路由（任务C Phase 4，供 AI Agent 8091 调用）**：GET /api/internal/sim-trade/profile?userId=，鉴权同 market_realtime；无交易用户返回字段齐全的空画像（behaviorTags=[NO_TRADE_RECORD]）；userId 缺失→SYSTEM_ERROR（对应 internal/SimTradeProfileController.java） |
| `admin/trade.py` | **管理端交易管理路由（任务B）**：GET /api/admin/trade/order/page 与 /api/admin/trade/deal/page 分页查询（pageNum/pageSize 默认 1/10，可选 userId/symbol，每页上限 1000；响应体对齐 MyBatis-Plus Page 序列化 {records,total,size,current,pages}）（对应 admin/TradeManageController.java） |

## app/task/ 定时任务包

| 英文文件 | 中文职责说明 |
| ---- | ---- |
| `__init__.py` | **任务生命周期入口（任务B 填充）**：start() 在启动钩子中绑定事件循环→执行订单恢复→启动 3 秒行情调度；stop() 在关闭钩子中取消调度循环并优雅关闭全部撮合队列（对应 Spring 容器托管 + @PreDestroy） |
| `market_data_scheduler_task.py` | **行情调度任务（任务B）**：每 3 秒遍历订单簿活跃 symbol（60 开头=sh 其余=sz，照抄原判定）拉腾讯实时行情→HybridOrderBook.processMarketData 触发撮合；单 symbol 失败不影响其他（对应 task/MarketDataSchedulerTask.java @Scheduled(fixedRate=3000)） |
| `order_recovery_task.py` | **订单恢复任务（任务B）**：启动时查询状态 1（待定）/2（部分完成）的未完成订单→逐单重新提交撮合队列→由 processTrade 重建进程内订单簿并恢复行情驱动；快照持久化方法按原 TODO 空实现仅保留日志语义（对应 task/OrderRecoveryTask.java @PostConstruct + @Scheduled(cron)） |
