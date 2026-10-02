#!/usr/bin/env bash
# ============================================================================
# 初始化环境 setup-env.sh —— 「量股化金」Python 复现环境部署
# 原则: 所有下载/部署全部隔离在 env/ 目录内, 不写系统目录、不注册 Windows 服务
# 用法: bash 初始化环境-setup-env.sh <venv|mysql|redis|status>
#       每个阶段幂等, 可重复执行 (中断后重跑会续着来)
# ============================================================================
set -u
# ===== 自定位（全相对路径，项目整体挪动不影响）=====
# 本脚本位于 env/ 内；项目根 = env/ 的上一级（其下有 lghj-python/）
ENVDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(dirname "$ENVDIR")"
LOGDIR="$ENVDIR/logs"
# init.sql 来源：优先项目内副本，兜底仍留在项目根之外的原 Java 仓库（若有）
SQL_SRC=""
for _C in "$BASE/lghj-python/sql/数据库初始化-init.sql" "$BASE/../lghj-web-dist.tar/feng-lghj/docs/dev-ops/sql/mysql/init.sql"; do
  [ -f "$_C" ] && { SQL_SRC="$_C"; break; }
done
# mysqld 不支持非 ASCII 路径：在用户目录下建 ASCII Junction 指向本 env/（数据实体仍在 env/ 内）
ENVASCII="$(cygpath -m "$USERPROFILE")/lghj-env"
STAGE="${1:-all}"
mkdir -p "$LOGDIR" "$ENVDIR/下载缓存-download-cache"

# 校验/修复 Junction：目标不是当前 env/ 时自动重建（项目文件夹挪动后无需手工处理）
ensure_junction() {
  local WJUNC WINENV VERDICT
  WJUNC="$(cygpath -w "$ENVASCII")"
  WINENV="$(cygpath -w "$ENVDIR")"
  VERDICT="$(powershell -NoProfile -Command "\$t=(Get-Item -LiteralPath '$WJUNC' -ErrorAction SilentlyContinue).Target; if(\$t -eq '$WINENV'){'OK'}else{'BAD'}" 2>/dev/null | tr -d '\r')"
  if [ "$VERDICT" = "OK" ]; then return 0; fi
  cmd //c rmdir "$WJUNC" >/dev/null 2>&1
  powershell -NoProfile -Command "New-Item -ItemType Junction -Path '$WJUNC' -Target '$WINENV' | Out-Null" \
    || { log "FATAL: 创建 Junction 失败"; return 1; }
  log "junction: $WJUNC -> $WINENV (已重建)"
}

log() { echo "[$(date '+%H:%M:%S')] $*"; }
port_up() { (echo >/dev/tcp/127.0.0.1/"$1") 2>/dev/null; }

# ---------------- 阶段 venv: 虚拟环境与 Python 依赖 ----------------
stage_venv() {
  local VENVDIR="$ENVDIR/venv-虚拟环境"
  local VENVPY="$VENVDIR/Scripts/python.exe"
  if [ ! -f "$VENVPY" ]; then
    log "venv: 创建虚拟环境 $VENVDIR (基础解释器自动探测, 可用 LGHJ_BASE_PYTHON 指定)"
    local PYBASE="${LGHJ_BASE_PYTHON:-$(command -v python 2>/dev/null || true)}"
    [ -n "$PYBASE" ] || { log "FATAL: 未找到基础 Python, 请 export LGHJ_BASE_PYTHON=<python.exe 路径>"; return 1; }
    uv venv "$VENVDIR" --python "$PYBASE" || { log "FATAL: venv 创建失败"; return 1; }
  fi
  export UV_CACHE_DIR="$ENVDIR/下载缓存-download-cache/uv"
  export PIP_CACHE_DIR="$ENVDIR/下载缓存-download-cache/pip"
  local MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
  log "venv: 安装基础依赖 (清华镜像)"
  uv pip install --python "$VENVPY" -i "$MIRROR" \
    fastapi "uvicorn[standard]" pydantic pydantic-settings \
    sqlalchemy pymysql cryptography redis httpx pyjwt \
    openpyxl pandas numpy python-multipart litellm pytest \
    || { log "FATAL: 基础依赖安装失败"; return 1; }
  log "venv: 安装 torch (CPU 版, 体积大, 失败不阻塞)"
  uv pip install --python "$VENVPY" -i "$MIRROR" torch \
    || log "WARN: torch 安装失败, 预测服务训练阶段需重试"
  log "venv: 当前已装清单:"
  "$VENVPY" -m pip list 2>/dev/null | tail -n +3
}

# ---------------- 阶段 mysql: 免安装版 MySQL 8 ----------------
stage_mysql() {
  ensure_junction
  local MDIR="$ENVASCII/db-mysql8"
  local DATADIR="$ENVASCII/mysql8-data"
  local ZIP="$ENVDIR/下载缓存-download-cache/mysql8.zip"
  if [ ! -f "$MDIR/bin/mysqld.exe" ]; then
    log "mysql: 下载免安装版 zip (清华镜像, 约 200MB)"
    local OK=0 U
    for U in \
      "https://cdn.mysql.com//archives/mysql-8.0/mysql-8.0.42-winx64.zip" \
      "https://mirrors.huaweicloud.com/mysql/Downloads/MySQL-8.0/mysql-8.0.29-winx64.zip" \
      "https://mirrors.aliyun.com/mysql/MySQL-8.0/mysql-8.0.28-winx64.zip"; do
      log "mysql: 尝试 $U"
      if curl -fL --ssl-no-revoke --retry 2 --connect-timeout 20 -o "$ZIP" "$U" \
         && [ "$(stat -c%s "$ZIP" 2>/dev/null || echo 0)" -gt 100000000 ]; then OK=1; break; fi
    done
    [ "$OK" = 1 ] || { log "FATAL: MySQL 下载失败"; return 1; }
    log "mysql: 解压"
    powershell -NoProfile -Command "Expand-Archive -LiteralPath '$ZIP' -DestinationPath '$ENVDIR/下载缓存-download-cache/mysql8-extract' -Force" \
      || { log "FATAL: 解压失败"; return 1; }
    local SRC
    SRC=$(find "$ENVDIR/下载缓存-download-cache/mysql8-extract" -maxdepth 1 -type d -name "mysql*" | head -1)
    rm -rf "$MDIR"
    if [ -n "$SRC" ]; then
      mv "$SRC" "$MDIR" 2>/dev/null || { cp -r "$SRC" "$MDIR" && rm -rf "$SRC"; } \
        || { log "FATAL: 移动目录失败"; return 1; }
    fi
  fi
  # 兼容 zip 内多一层 mysql-8.0.x-winx64 目录的情况
  if [ ! -f "$MDIR/bin/mysqld.exe" ]; then
    local INNER BINDIR
    INNER=$(find "$MDIR" -maxdepth 3 -type f -name "mysqld.exe" 2>/dev/null | head -1)
    if [ -n "$INNER" ]; then
      BINDIR=$(dirname "$(dirname "$INNER")")
      log "mysql: 修正嵌套目录布局 ($BINDIR -> $MDIR)"
      mv "$BINDIR"/* "$MDIR"/ 2>/dev/null
    fi
  fi
  [ -f "$MDIR/bin/mysqld.exe" ] || { log "FATAL: 仍找不到 mysqld.exe"; return 1; }
  if port_up 3306; then log "SKIP: 3306 已被占用, 假定已有 MySQL 在运行"; return 0; fi
  if [ ! -d "$DATADIR/mysql" ]; then
    log "mysql: 初始化数据目录 (root 空密码 bootstrap)"
    cat > "$MDIR/my.ini" <<EOF
[mysqld]
basedir=$MDIR
datadir=$DATADIR
port=3306
character-set-server=utf8mb4
collation-server=utf8mb4_general_ci
max_allowed_packet=64M
[client]
port=3306
default-character-set=utf8mb4
EOF
    "$MDIR/bin/mysqld.exe" --defaults-file="$MDIR/my.ini" --initialize-insecure --console \
      > "$LOGDIR/mysql初始化-init.log" 2>&1 \
      || { log "FATAL: mysqld --initialize 失败, 见 $LOGDIR/mysql初始化-init.log"; return 1; }
  fi
  log "mysql: 后台启动 mysqld (日志 $LOGDIR/mysql运行-run.log)"
  ( "$MDIR/bin/mysqld.exe" --defaults-file="$MDIR/my.ini" --console > "$LOGDIR/mysql运行-run.log" 2>&1 & )
  local i; for i in $(seq 1 60); do port_up 3306 && break; sleep 1; done
  port_up 3306 || { log "FATAL: mysqld 启动超时, 见运行日志"; return 1; }
  local MYSQL="$MDIR/bin/mysql.exe"
  log "mysql: 建库与账号 (幂等)"
  if "$MYSQL" -uroot -p123456 -h127.0.0.1 -e "SELECT 1" >/dev/null 2>&1; then
    log "mysql: 密码已设置, 仅确保 lghj 库存在"
    "$MYSQL" -uroot -p123456 -h127.0.0.1 -e "CREATE DATABASE IF NOT EXISTS lghj CHARACTER SET utf8mb4;" \
      || { log "FATAL: 建库失败"; return 1; }
  else
    "$MYSQL" -uroot --skip-password -e \
      "ALTER USER 'root'@'localhost' IDENTIFIED BY '123456';
       CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY '123456';
       GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;
       CREATE DATABASE IF NOT EXISTS lghj CHARACTER SET utf8mb4;" \
      || { log "FATAL: 账号/建库失败"; return 1; }
  fi
  local TBL
  TBL=$("$MYSQL" -uroot -p123456 -h127.0.0.1 -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='lghj';" 2>/dev/null)
  if [ "${TBL:-0}" -eq 0 ]; then
    if [ -z "$SQL_SRC" ]; then log "FATAL: 找不到 init.sql (lghj-python/sql/ 内无副本)"; return 1; fi
    log "mysql: 导入 init.sql (原 15 张表)"
    "$MYSQL" -uroot -p123456 -h127.0.0.1 lghj < "$SQL_SRC" \
      && log "OK: init.sql 导入完成" || { log "FATAL: init.sql 导入失败"; return 1; }
  else
    log "SKIP: lghj 已有 ${TBL} 张表, 跳过导入"
  fi
}

# ---------------- 阶段 redis: Windows 版 Redis ----------------
stage_redis() {
  local RDIR="$ENVDIR/cache-redis-缓存"
  local ZIP="$ENVDIR/下载缓存-download-cache/redis-win.zip"
  if [ ! -f "$RDIR/redis-server.exe" ]; then
    log "redis: 下载 Windows 版 (tporadowski 5.0.14, 备用镜像轮询)"
    local OK=0 U
    for U in \
      "https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip" \
      "https://gh-proxy.com/https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip" \
      "https://ghfast.top/https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip"; do
      log "redis: 尝试 $U"
      if curl -fL --ssl-no-revoke --retry 2 --connect-timeout 15 -o "$ZIP" "$U" && [ -s "$ZIP" ]; then OK=1; break; fi
    done
    [ "$OK" = 1 ] || { log "FATAL: Redis 下载失败"; return 1; }
    powershell -NoProfile -Command "Expand-Archive -LiteralPath '$ZIP' -DestinationPath '$RDIR' -Force" \
      || { log "FATAL: Redis 解压失败"; return 1; }
  fi
  if port_up 6379; then log "SKIP: 6379 已在运行"; return 0; fi
  mkdir -p "$ENVDIR/redis数据-data"
  log "redis: 后台启动 (日志 $LOGDIR/redis运行-run.log)"
  ( "$RDIR/redis-server.exe" --port 6379 --dir "$ENVDIR/redis数据-data" > "$LOGDIR/redis运行-run.log" 2>&1 & )
  sleep 2; port_up 6379 && log "OK: redis 已启动" || { log "FATAL: redis 启动失败"; return 1; }
}

# ---------------- 阶段 status: 环境体检 ----------------
stage_status() {
  local VENVPY="$ENVDIR/venv-虚拟环境/Scripts/python.exe"
  echo "== 环境体检 =="
  [ -f "$VENVPY" ] && echo "venv: OK ($("$VENVPY" --version 2>&1))" || echo "venv: 未创建"
  port_up 3306 && echo "mysql: 3306 在线" || echo "mysql: 3306 不在线"
  port_up 6379 && echo "redis: 6379 在线" || echo "redis: 6379 不在线"
  ensure_junction 2>/dev/null || true
  if port_up 3306 && [ -f "$ENVASCII/db-mysql8/bin/mysql.exe" ]; then
    "$ENVASCII/db-mysql8/bin/mysql.exe" -uroot -p123456 -e "USE lghj; SHOW TABLES;" 2>/dev/null \
      && echo "lghj 库: 可访问" || echo "lghj 库: 不可访问或未导入"
  fi
}

case "$STAGE" in
  venv)   stage_venv ;;
  mysql)  stage_mysql ;;
  redis)  stage_redis ;;
  status) stage_status ;;
  all)    stage_venv; stage_mysql; stage_redis; stage_status ;;
  *) echo "用法: bash 初始化环境-setup-env.sh <venv|mysql|redis|status>"; exit 1 ;;
esac
