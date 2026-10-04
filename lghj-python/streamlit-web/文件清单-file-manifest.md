# 文件清单 - File Manifest（量股化金 · Streamlit 前端 streamlit-web）

以 **Streamlit** 复现原 Vue 前端（参考同花顺界面风格：深色终端底、红色主色调、涨红跌绿），
对接同一套 Python 三后端（8080 主服务 / 8091 AI Agent / 8001 预测），接口契约与原前端完全一致。

## 目录结构

| 文件 / 目录 | 中文职责说明 |
| --- | --- |
| `streamlit_app.py` | 入口：页面配置（宽布局）、`st.navigation` 分组导航（**未登录=仅登录页的独立登录屏；登录后=完整应用**（交易终端/智能服务，管理端仅 userType=3））、**马维斯式侧栏（本工程扩展）**：**置顶栏（品牌 → ＋新建对话 → ▸管家团队，压在页面导航之上；框架自动导航被 CSS 隐藏，页面导航改由 `st.page_link` 自渲染在管家团队下方，当前页高亮）**、新建对话（回队长模式自动调度）、管家团队（**折叠式默认收起**，队长+6 专家按钮，点击单独对话并自动收起）、个人知识库（上传 txt/md、删除，投顾可检索引用）、历史对话（固定高度可滑动列表，点击回看/续聊、可删除）、账户行固定左下角（**ZCode 式单行：头像 + 用户名 + 角色徽章 + 右端退出图标**；绝对定位锚定侧栏本身——侧栏内联宽度随拉伸实时更新，`left:0/right:0` 自动跟随，中间 relative 祖先（滚动容器/元素容器）经 CSS 转为 static 防止锚错父级或随内容滚动））；**侧栏渲染先于 `st.navigation().run()`**（页面脚本中的 `st.stop()`——如自选股为空、交易页未开户——会中断整个脚本，侧栏后置时会被砍掉导致置顶栏消失） |
| `app_pages/登录-login.py` | 独立登录/注册页（与主应用完全分离：隐藏侧栏与导航）：右上角缩小版品牌图标（红色渐变小方块+名称，自定义 HTML）、居中「欢迎登录」卡片（登 录/注 册 标签），登录成功 rerun 进入行情首页；未登录访问任何应用页 URL 都回落到本页 |
| `api.py` | 三后端 API 客户端：Result/Response/裸 JSON 三种响应体适配、token 头注入、401 强制登出、登录注册、行情/K线/分时/预测/新闻、自选、账户交易、社区、AI 投顾（chat/trace/agent_team/**历史×3/知识库×3** 扩展接口）、管理端全量封装；行情/ K线带 `st.cache_data` 短缓存 |
| `components.py` | 同花顺风格共享组件：涨红跌绿配色与 Styler 着色、个股行情头部（大字现价+涨跌箭头）、三大指数看板、ECharts 图表 option 构造（K线蜡烛+MA+成交量、分时白价黄均、预测历史实线+未来红色虚线）；**Agent 可视化组件（本工程扩展）**：管家卡片映射表与 agent_card/agent_card_name 助手、轨迹切片 slice_current_run、状态推导 agent_team_status、思考芯片流 agent_thinking_stream/render_thinking_chips（🧠决策/🔧工具/➡️转交/📤输出；实时与回放共用一渲染） |
| `.streamlit/config.toml` | 同花顺风格主题（基于官方 financial-dashboard 模板改造）：**浅色版**——白底 #FFFFFF、浅灰侧栏 #F7F8FA、主色 THS 红 #E64545、语义色白底加深变体（红涨 #E64545 / 绿跌 #00A67D / 均价线深黄 #D48806 / 蓝 #2563EB / 紫 #7C3AED）；原深色版（深底 #0E1114）已整体切换为浅色 |
| `app_pages/行情-market.py` | 行情页：三大指数（5 秒 fragment 自刷新）、股票搜索（LIKE，点击行进个股）、自选速览 |
| `app_pages/个股-stock.py` | 个股页：实时行情头部（5 秒自刷新）、加/移自选、四个懒加载标签（分时/K线 D-W-M/AI 预测/新闻） |
| `app_pages/交易-trade.py` | 模拟交易页：开户、账户指标、买卖委托表单（query 传参契约）、撤单、持仓（实时价计算市值/浮盈，涨红跌绿）、委托/成交记录 |
| `app_pages/自选-watchlist.py` | 自选股页：现价/涨跌幅着色列表，选中行可跳个股或移除 |
| `app_pages/AI投顾-advisor.py` | AI 投顾页（**ZCode 式思考流终端，本工程扩展**）：侧栏管家选择/历史回看联动、当前管家头栏、后台线程 chat + 每 2 秒轮询轨迹——**思考过程在回答之前（回答气泡内上方「深度思考中…·已N步」实时展开，完成后收起为「已深度思考·N步」，历史消息同样回放；🧠决策耗时/🔧工具可展开看入参结果/➡️转交/📤输出）** + 生成期间右上角"⚡N 位管家正在工作中"指示、建议 pills（**点击即提问，与聊天输入框共用 `_submit_question` 提交路径**——修复了 pills 只落消息不触发后端对话的 bug）、清空对话（原管家卡片条已按需求移除，状态推导仅用于工作指示） |
| `app_pages/社区-community.py` | 社区页：热门/我的/关注流/按用户四标签、发布博客（**context 字段契约**）、点赞、关注作者、二级评论树（回复/点赞/删除）、翻页 |
| `app_pages/管理端-admin.py` | 管理端：用户（列表+新增；原系统 UserVO 无 id，启停/删除受限）、股票（列表+按代码幂等更新）、博客/评论（删除，评论用 ButtonColumn）、委托/成交双栏分页 |
| `启动前端-run-web.bat` | 一键启动（8501），相对路径，GBK 编码 |

## 启动顺序

```bash
# 1. 中间件（env/ 一键脚本）
bash ../../env/初始化环境-setup-env.sh mysql
bash ../../env/初始化环境-setup-env.sh redis
# 2. 三个后端（lghj-python 下的 启动三服务-run-all-services.bat）
# 3. 本前端：双击 启动前端-run-web.bat，或：
cd streamlit-web && "../../env/venv-虚拟环境/Scripts/python.exe" -m streamlit run streamlit_app.py --server.port 8501
```

## 登录账号

- 管理员：`admin` / `123456`（userType=3，可见管理端）
- 普通用户：侧栏「注册」自助创建

## 设计说明（与原 Vue 前端的差异）

- 原前端为 Vue3 + Element Plus + ECharts；本前端为 Streamlit 单进程应用，页面即脚本
- 三种响应体适配逻辑与原 request.js 拦截器语义一致；鉴权头仍为 `token`
- 涨红跌绿遵循中国证券惯例（浅色主题取加深变体保证白底对比度）；图表用 Streamlit 原生 `st.echarts_chart`（ECharts 蜡烛图与 THS 同源视觉），轴/分割线/tooltip 配色随浅色主题调整
- `get_excel`（预测导出）为原前端死接口（后端无路由），不复现
- 侧栏「管家团队/知识库/历史对话/底部账户卡」与 AI 投顾页执行过程可视化为本工程扩展
  （依赖 8091 的 trace/agent_team/history_*/kb_* 扩展接口，原 Java 无；详见
  ../ai-agent-server/文件清单-file-manifest.md）；8091 未提供扩展接口时 AI 投顾页
  自动降级隐藏卡片条，对话功能不受影响
- 历史会话存在 MySQL（agent_chat_* 扩展表）；注意 8091 重启后内存会话丢失，
  历史回看可续聊但 LLM 上下文不回放（续聊按新上下文处理）
