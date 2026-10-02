# 文件清单 - File Manifest（量股化金 · Streamlit 前端 streamlit-web）

以 **Streamlit** 复现原 Vue 前端（参考同花顺界面风格：深色终端底、红色主色调、涨红跌绿），
对接同一套 Python 三后端（8080 主服务 / 8091 AI Agent / 8001 预测），接口契约与原前端完全一致。

## 目录结构

| 文件 / 目录 | 中文职责说明 |
| --- | --- |
| `streamlit_app.py` | 入口：页面配置（宽布局）、`st.navigation` 分组导航（**未登录=仅登录页的独立登录屏；登录后=完整应用**（交易终端/智能服务，管理端仅 userType=3））、侧栏用户卡片 |
| `app_pages/登录-login.py` | 独立登录/注册页（与主应用完全分离：隐藏侧栏与导航）：右上角缩小版品牌图标（红色渐变小方块+名称，自定义 HTML）、居中「欢迎登录」卡片（登 录/注 册 标签），登录成功 rerun 进入行情首页；未登录访问任何应用页 URL 都回落到本页 |
| `api.py` | 三后端 API 客户端：Result/Response/裸 JSON 三种响应体适配、token 头注入、401 强制登出、登录注册、行情/K线/分时/预测/新闻、自选、账户交易、社区、AI 投顾、管理端全量封装；行情/ K线带 `st.cache_data` 短缓存 |
| `components.py` | 同花顺风格共享组件：涨红跌绿配色与 Styler 着色、个股行情头部（大字现价+涨跌箭头）、三大指数看板、ECharts 图表 option 构造（K线蜡烛+MA+成交量、分时白价黄均、预测历史实线+未来红色虚线） |
| `.streamlit/config.toml` | 同花顺风格主题（基于官方 financial-dashboard 模板改造）：深底 #0E1114、主色 THS 红 #E64545、语义色红涨 #FF5B5B / 绿跌 #00C08B |
| `app_pages/行情-market.py` | 行情页：三大指数（5 秒 fragment 自刷新）、股票搜索（LIKE，点击行进个股）、自选速览 |
| `app_pages/个股-stock.py` | 个股页：实时行情头部（5 秒自刷新）、加/移自选、四个懒加载标签（分时/K线 D-W-M/AI 预测/新闻） |
| `app_pages/交易-trade.py` | 模拟交易页：开户、账户指标、买卖委托表单（query 传参契约）、撤单、持仓（实时价计算市值/浮盈，涨红跌绿）、委托/成交记录 |
| `app_pages/自选-watchlist.py` | 自选股页：现价/涨跌幅着色列表，选中行可跳个股或移除 |
| `app_pages/AI投顾-advisor.py` | AI 投顾页：智能体选择、会话幂等复用、chat 对话（含建议 pills、清空对话） |
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
- 涨红跌绿遵循中国证券惯例；图表用 Streamlit 原生 `st.echarts_chart`（ECharts 蜡烛图与 THS 同源视觉）
- `get_excel`（预测导出）为原前端死接口（后端无路由），不复现
