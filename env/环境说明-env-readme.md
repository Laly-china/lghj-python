# 环境说明 env-readme.md

「量股化金」Python 复现的**隔离运行环境**。所有下载与部署物全部收在本 `env/` 目录内，不写系统目录、不注册 Windows 服务、不改全局 Python。

**位置无关**：`初始化环境-setup-env.sh` 按脚本自身位置自定位（项目根 = `env/` 的上一级，其下应有 `lghj-python/`），整个项目文件夹挪动到任何位置都不需要改脚本；文档中的解释器路径均为相对写法（服务目录下 `../../env/...`）。

## 目录结构

| 目录 / 文件 | 说明 |
|---|---|
| `venv-虚拟环境/` | Python 3.13 虚拟环境（首次创建时自动探测基础解释器，也可用环境变量 `LGHJ_BASE_PYTHON` 指定）。**使用方式：直接调用 `venv-虚拟环境/Scripts/python.exe`，不要 activate** |
| `db-mysql8/` | MySQL 8.0.42 免安装版（⚠️ 目录名保持纯 ASCII，mysqld 不支持非 ASCII 路径） |
| `mysql8-data/` | MySQL 数据目录（由 `mysqld --initialize` 生成，纯 ASCII 同上） |
| `cache-redis-缓存/` | Redis 5.0.14 Windows 版（tporadowski 发行版） |
| `redis数据-data/` | Redis 持久化目录 |
| `下载缓存-download-cache/` | 安装包与 pip/uv 下载缓存（uv、pip 缓存均重定向到这里） |
| `logs/` | mysqld / redis / 部署脚本运行日志 |
| `初始化环境-setup-env.sh` | 一键部署脚本（幂等，可反复执行） |

## ASCII 联结（Junction）——工程约束说明

MySQL 的 `mysqld.exe` 无法处理中文路径（`my.ini` 按 ANSI 读取会乱码），而本项目路径含中文。因此：

- 脚本会在**当前 Windows 用户目录**下建目录联结 **`<用户目录>\lghj-env` → 本 `env/` 目录**（仅是指针，数据实体仍在 env/ 内，路径不含机器/用户相关的硬编码）
- `my.ini` / 启动命令一律使用该 ASCII 联结路径访问 `db-mysql8`、`mysql8-data`
- **自动修复**：每次执行脚本的 `mysql`/`status` 阶段都会校验联结目标；项目文件夹挪动后目标不符时自动删除重建，无需手工处理
- 删除联结不影响任何数据；手工重建：`powershell New-Item -ItemType Junction -Path '<用户目录>\lghj-env' -Target '<项目根>\env'`

## 中间件连接信息（三个 Python 服务共用）

| 中间件 | 地址 | 账号 |
|---|---|---|
| MySQL 8.0.42 | `127.0.0.1:3306`，库名 `lghj` | `root` / `123456` |
| Redis | `127.0.0.1:6379`，database `8` | 无密码 |

## 启动 / 停止 / 体检

```bash
bash env/初始化环境-setup-env.sh mysql    # 启动 MySQL（已启动则跳过）
bash env/初始化环境-setup-env.sh redis    # 启动 Redis（已启动则跳过）
bash env/初始化环境-setup-env.sh status   # 环境体检（venv/端口/库表）
```

脚本幂等：重复执行会自动跳过已完成的步骤；中断后重跑会续着来。停止服务直接结束对应进程（mysqld.exe / redis-server.exe）即可。

## Python 依赖

- 已预装：fastapi、uvicorn[standard]、pydantic、pydantic-settings、sqlalchemy、pymysql、cryptography、redis、httpx、pyjwt、openpyxl、pandas、numpy、python-multipart、litellm、akshare、torch(CPU)、pytest
- 补装命令：`"env/venv-虚拟环境/Scripts/python.exe" -m pip install 包名`（本机网络下清华 PyPI 镜像不通，**直接用官方 PyPI**）

## 本机网络已知约束（部署脚本已内置应对）

- Git Bash 自带 curl 走 Windows schannel，会报 `CRYPT_E_REVOCATION_FAILED` → 所有 curl 已加 `--ssl-no-revoke`
- GitHub 直连可用（加上述参数后）；`gh-proxy`/`ghfast` 类加速镜像在本机反而超时
- MySQL 安装包源：官网 CDN（`cdn.mysql.com`）→ 华为云 → 阿里云 逐级回退；Redis 用 GitHub Releases

## 命名规则例外清单

用户要求所有文件中文-english 双语命名；以下因**工具链硬约束**保留纯 ASCII（mysqld 路径限制 / Python import 机制）：`db-mysql8/`、`mysql8-data/`、各服务 `app/` 源码包、`main.py` 等——其余文件均为双语命名，各服务目录内有 `文件清单-file-manifest.md` 对照说明。
