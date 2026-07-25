#!/usr/bin/env bash
#
# deploy/scripts/deploy.sh —— 服务器侧部署封装脚本（Deployer / Components 3）
#
# 职责（对应 design.md "服务器侧脚本接口" 与 R4.2 / R4.3 / R5.2 / R4.5）：
#   1. 将密钥与 compose 变量写入 ${APP_DIR}/.env.prod（chmod 600，非仓库追踪）。
#   2. git fetch && git checkout <SHA>，使 docker-compose.prod.yml 与脚本同步到部署版本。
#   3. docker login ghcr.io → docker compose pull（300s 超时，R4.2）。
#   4. docker compose up -d，并在 120s 内轮询确认 backend/worker/web/redis 四服务
#      进入 running（R4.3），running 判定复用 lib/retry.py::services_all_running。
#   5. 一旦开始拉取/重启即输出 deploy_attempted=true（写入 $GITHUB_OUTPUT 或 stdout 标记），
#      供编排层（rollback 门控）捕获。
#
# 设计原则：set -euo pipefail，Fail-Fast；任一阶段失败即非零退出，触发上层回滚（R4.5）。
# 安全：所有密钥/配置均从环境变量读取，绝不硬编码；日志仅打印变量名，不回显密钥值。
#
# 期望由 CI 的 SSH 步骤通过 envs: 注入以下环境变量：
#   必需密钥：     AUS_ELE_JWT_SECRET、FINGRID_API_KEY
#   镜像寻址：     IMAGE_TAG、REGISTRY(默认 ghcr.io)、IMAGE_PREFIX
#   GHCR 登录：    GHCR_USERNAME、GHCR_TOKEN
#   compose 端口： API_HOST_PORT(默认 18085)、WEB_HOST_PORT(默认 18080)
#   可选：         APP_DIR(默认 /www/wwwroot/aus-ele)、COMPOSE_FILE(默认 docker-compose.prod.yml)
#                  GIT_SHA(默认取 IMAGE_TAG)、PULL_TIMEOUT_S(默认 300)、
#                  RUNNING_WINDOW_S(默认 120)、RUNNING_INTERVAL_S(默认 5)

set -euo pipefail

# ---------------------------------------------------------------------------
# 配置（全部可由环境变量覆盖，提供合理默认值）
# ---------------------------------------------------------------------------
APP_DIR="${APP_DIR:-/www/wwwroot/aus-ele}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${APP_DIR}/.env.prod"
REGISTRY="${REGISTRY:-ghcr.io}"
PULL_TIMEOUT_S="${PULL_TIMEOUT_S:-300}"
RUNNING_WINDOW_S="${RUNNING_WINDOW_S:-120}"
RUNNING_INTERVAL_S="${RUNNING_INTERVAL_S:-5}"

# 部署版本：优先使用显式 GIT_SHA，否则回退到 IMAGE_TAG（二者均为 40 位 commit SHA）。
GIT_SHA="${GIT_SHA:-${IMAGE_TAG:-}}"

# 必需进入 running 状态的服务集合（R4.3）。
REQUIRED_SERVICES="backend worker web redis postgres"

# lib 目录（deploy/scripts/lib），用于通过 python3 调用 services_all_running。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
LIB_PARENT="${SCRIPT_DIR}"

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

# log: 统一阶段日志，输出到 stderr，绝不打印密钥值。
log() {
    echo "[deploy] $*" >&2
}

# fail: 打印错误并以非零退出（Fail-Fast，触发上层回滚 R4.5）。
fail() {
    echo "[deploy][ERROR] $*" >&2
    exit 1
}

# emit_deploy_attempted: 标记部署已开始拉取/重启（R4.5 回滚门控依据）。
# 写入 $GITHUB_OUTPUT（若存在）并同时输出 stdout 标记，供编排层捕获。
emit_deploy_attempted() {
    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
        echo "deploy_attempted=true" >>"${GITHUB_OUTPUT}"
    fi
    echo "deploy_attempted=true"
}

# require_env: 确认指定环境变量存在且非空，仅报告变量名（不回显值）。
require_env() {
    local name="$1"
    local value="${!name:-}"
    if [[ -z "${value}" ]]; then
        fail "必需环境变量缺失或为空: ${name}"
    fi
}

# require_cmd: 确认依赖的外部命令可用。
require_cmd() {
    local cmd="$1"
    command -v "${cmd}" >/dev/null 2>&1 || fail "缺少必需命令: ${cmd}"
}

# ---------------------------------------------------------------------------
# 阶段 0：前置校验
# ---------------------------------------------------------------------------
preflight() {
    log "阶段 0/5：前置校验"

    require_cmd docker
    require_cmd git
    require_cmd python3
    require_cmd timeout

    # 必需密钥与镜像寻址变量（仅报告名称，不输出值）。
    require_env AUS_ELE_JWT_SECRET
    require_env FINGRID_API_KEY
    require_env IMAGE_PREFIX
    require_env GHCR_USERNAME
    require_env GHCR_TOKEN

    [[ -n "${GIT_SHA}" ]] || fail "必需环境变量缺失或为空: GIT_SHA/IMAGE_TAG"

    [[ -d "${APP_DIR}" ]] || fail "部署目录不存在: ${APP_DIR}"

    log "前置校验通过（APP_DIR=${APP_DIR}, REGISTRY=${REGISTRY}, IMAGE_PREFIX=${IMAGE_PREFIX}）"
}

# ---------------------------------------------------------------------------
# 阶段 1：写 .env.prod（chmod 600）
# ---------------------------------------------------------------------------
write_env_file() {
    log "阶段 1/5：写入 ${ENV_FILE}（chmod 600）"

    # 先以 600 创建空文件再写入，避免写入瞬间存在更宽松权限的窗口。
    umask 077
    : >"${ENV_FILE}"
    chmod 600 "${ENV_FILE}"

    # compose 变量替换所需的运行时值（含密钥）。日志不打印任何值。
    {
        echo "# 由 deploy.sh 生成，请勿手工编辑；包含密钥，权限 600，非仓库追踪。"
        echo "REGISTRY=${REGISTRY}"
        echo "IMAGE_PREFIX=${IMAGE_PREFIX}"
        echo "IMAGE_TAG=${IMAGE_TAG:-${GIT_SHA}}"
        echo "API_HOST_PORT=${API_HOST_PORT:-18085}"
        echo "WEB_HOST_PORT=${WEB_HOST_PORT:-18080}"
        echo "PG_HOST_PORT=${PG_HOST_PORT:-15432}"
        echo "AUS_ELE_JWT_SECRET=${AUS_ELE_JWT_SECRET}"
        echo "FINGRID_API_KEY=${FINGRID_API_KEY}"
        echo "AUS_ELE_PG_PASSWORD=${AUS_ELE_PG_PASSWORD:-aemo_pg_pass_2026}"
        # AI Agent LLM 配置（U6）
        echo "AUS_ELE_AGENT_LLM_PROVIDER=${AUS_ELE_AGENT_LLM_PROVIDER:-openai}"
        echo "AUS_ELE_AGENT_LLM_API_KEY=${AUS_ELE_AGENT_LLM_API_KEY:-}"
        echo "AUS_ELE_AGENT_LLM_BASE_URL=${AUS_ELE_AGENT_LLM_BASE_URL:-}"
        echo "AUS_ELE_AGENT_LLM_MODEL=${AUS_ELE_AGENT_LLM_MODEL:-gpt-4o}"
        # CORS（生产域名）
        echo "AUS_ELE_CORS_ALLOW_ORIGINS=${AUS_ELE_CORS_ALLOW_ORIGINS:-}"
    } >>"${ENV_FILE}"

    log ".env.prod 写入完成（含变量: REGISTRY, IMAGE_PREFIX, IMAGE_TAG, ports, JWT, FINGRID, LLM, CORS）"
}

# ---------------------------------------------------------------------------
# 阶段 2：git fetch && git checkout <SHA>
# ---------------------------------------------------------------------------
checkout_revision() {
    log "阶段 2/5：同步部署版本到 ${GIT_SHA}"

    git -C "${APP_DIR}" fetch --all --prune || fail "git fetch 失败"
    git -C "${APP_DIR}" checkout --force "${GIT_SHA}" || fail "git checkout ${GIT_SHA} 失败"

    [[ -f "${APP_DIR}/${COMPOSE_FILE}" ]] || fail "检出后未找到编排文件: ${APP_DIR}/${COMPOSE_FILE}"

    log "已检出 ${GIT_SHA}，编排文件就绪: ${COMPOSE_FILE}"
}

# ---------------------------------------------------------------------------
# 阶段 3：docker login + pull（300s 超时，R4.2）
# ---------------------------------------------------------------------------
login_and_pull() {
    log "阶段 3/5：登录 ${REGISTRY} 并拉取镜像（超时 ${PULL_TIMEOUT_S}s）"

    # 经 stdin 传入 token，避免出现在进程参数表中。
    echo "${GHCR_TOKEN}" | docker login "${REGISTRY}" \
        --username "${GHCR_USERNAME}" --password-stdin >/dev/null 2>&1 \
        || fail "docker login ${REGISTRY} 失败"
    log "docker login ${REGISTRY} 成功"

    # 自此开始触及镜像拉取/重启 —— 标记 deploy_attempted（R4.5）。
    emit_deploy_attempted

    if ! timeout "${PULL_TIMEOUT_S}" \
        docker compose -f "${APP_DIR}/${COMPOSE_FILE}" --env-file "${ENV_FILE}" pull; then
        fail "docker compose pull 失败或超时（>${PULL_TIMEOUT_S}s），触发回滚"
    fi
    log "镜像拉取完成"
}

# ---------------------------------------------------------------------------
# 阶段 4：docker compose up -d
# ---------------------------------------------------------------------------
compose_up() {
    log "阶段 4/5：启动服务（compose up -d）"

    docker compose -f "${APP_DIR}/${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d \
        || fail "docker compose up -d 失败，触发回滚"

    log "compose up -d 已下发，开始确认服务运行状态"
}

# all_running: 调用 lib/retry.py::services_all_running 判定四服务是否全部 running。
# 通过解析 `docker compose ps --format json` 构造 服务名->状态 映射后传给纯函数。
all_running() {
    local ps_json
    ps_json="$(docker compose -f "${APP_DIR}/${COMPOSE_FILE}" --env-file "${ENV_FILE}" \
        ps --format json 2>/dev/null)" || return 1

    PYTHONPATH="${LIB_PARENT}" REQUIRED_SERVICES="${REQUIRED_SERVICES}" \
        python3 -c '
import json
import os
import sys

from lib.retry import services_all_running

raw = sys.stdin.read().strip()
status = {}
if raw:
    # docker compose ps --format json 可能输出：
    #   - 每行一个 JSON 对象（较新版本）
    #   - 单个 JSON 数组
    try:
        parsed = json.loads(raw)
        records = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    for rec in records:
        name = rec.get("Service") or rec.get("Name")
        state = rec.get("State") or rec.get("Status") or ""
        if name:
            status[name] = state

required = os.environ.get("REQUIRED_SERVICES", "").split()
sys.exit(0 if services_all_running(status, required) else 1)
' <<<"${ps_json}"
}

# wait_for_running: 在 RUNNING_WINDOW_S 内轮询确认四服务进入 running（R4.3）。
wait_for_running() {
    log "阶段 5/5：在 ${RUNNING_WINDOW_S}s 内轮询确认服务 running: ${REQUIRED_SERVICES}"

    local deadline
    deadline=$(( $(date +%s) + RUNNING_WINDOW_S ))

    while true; do
        if all_running; then
            log "所有必需服务已进入 running 状态"
            return 0
        fi
        if (( $(date +%s) >= deadline )); then
            log "当前服务状态快照（用于诊断）："
            docker compose -f "${APP_DIR}/${COMPOSE_FILE}" --env-file "${ENV_FILE}" ps >&2 || true
            fail "服务未在 ${RUNNING_WINDOW_S}s 内全部进入 running，触发回滚（R4.5）"
        fi
        sleep "${RUNNING_INTERVAL_S}"
    done
}

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
main() {
    log "开始部署：GIT_SHA=${GIT_SHA}"
    preflight
    write_env_file
    checkout_revision
    login_and_pull
    compose_up
    wait_for_running
    log "部署成功完成：GIT_SHA=${GIT_SHA}"
}

main "$@"
