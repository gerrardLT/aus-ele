#!/usr/bin/env bash
#
# rollback.sh — 服务器侧失败自动回滚脚本（CI/CD 流水线 rollback 作业）。
#
# 职责（对应 design.md Components 5 与 R7.1–7.5 / R9.3 / R9.4）：
#   1. 读取 Last_Stable_Tag（state/last_stable_tag），调用 lib.stable_tag::decide_rollback
#      判定是否存在可回滚版本：
#        - 无可回滚版本（不存在 / 为空 / 非法 SHA）→ 跳过回滚、以失败收场并报告原因
#          （R7.3、R9.4）。
#   2. 存在合法 Last_Stable_Tag → 以该 SHA 作为 IMAGE_TAG，
#      `docker compose -f docker-compose.prod.yml --env-file .env.prod pull && up -d`
#      重启 backend/worker/web（R7.1）。
#   3. 回滚后 Health_Check：最多 5 次、间隔 10s、单次超时 10s、总窗口 60s，
#      复用 lib.retry::retry_succeeds 与 RetryConfig(5, 10, 10, 60)（R7.2）。
#        - 成功 → 以失败状态结束并报告「已回滚到 <Last_Stable_Tag>」（R7.4）。
#        - 失败 → 以失败状态结束、报告「回滚失败需人工介入」、保留当前状态（R7.5）。
#   4. 记录触发回滚的失败项（ROLLBACK_REASON）与回滚目标 SHA（R9.3）。
#
# 重要语义：
#   - 本脚本**总是**以非零退出码结束——即便回滚成功，本次流水线运行整体仍判定为失败
#     （R7.4）。不同退出码用于区分失败原因：
#       1  跳过回滚：无可回滚版本（首次部署 / 状态缺失 / 非法）。
#       2  已成功回滚到 Last_Stable_Tag（流水线仍记为失败）。
#       3  回滚失败，需人工介入（拉取/重启失败或回滚后健康检查未通过）。
#   - 使用 `set -uo pipefail` 而**不**使用 `-e`：回滚过程中单次健康探测失败属于正常
#     重试流程，必须显式处理各步骤退出码，绝不能因单次失败提前退出而跳过「需人工介入」
#     的报告逻辑。
#
# 可配置环境变量：
#   APP_DIR         部署根目录，默认 /www/wwwroot/aus-ele（含 docker-compose.prod.yml 与 .env.prod）。
#   API_HOST_PORT   后端宿主机端口，默认 18085（健康检查目标 127.0.0.1:<port>/api/health）。
#   ROLLBACK_REASON 触发本次回滚的失败项描述（如 "verify: Health_Check failed"），用于日志记录。
#   COMPOSE_FILE    生产编排文件名，默认 docker-compose.prod.yml。
#   ENV_FILE        环境变量文件名，默认 .env.prod。

set -uo pipefail

# ---------------------------------------------------------------------------
# 路径与可配置项
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

APP_DIR="${APP_DIR:-/www/wwwroot/aus-ele}"
API_HOST_PORT="${API_HOST_PORT:-18085}"
ROLLBACK_REASON="${ROLLBACK_REASON:-unknown}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.prod}"

STATE_FILE="${APP_DIR}/state/last_stable_tag"
HEALTH_URL="http://127.0.0.1:${API_HOST_PORT}/api/health"

# 回滚后 Health_Check 参数（R7.2）：最多 5 次、间隔 10s、单次超时 10s、总窗口 60s。
HEALTH_MAX_ATTEMPTS=5
HEALTH_INTERVAL_S=10
HEALTH_TIMEOUT_S=10

# 退出码常量（见文件头说明）。
EXIT_SKIP_NO_TARGET=1
EXIT_ROLLED_BACK=2
EXIT_MANUAL_INTERVENTION=3

# ---------------------------------------------------------------------------
# 日志辅助
# ---------------------------------------------------------------------------
log() {
    printf '[rollback %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

# 统一通过 lib 包调用纯函数：将脚本目录加入 PYTHONPATH，以 `lib.<module>` 导入，
# 使包内相对导入（from .validate import ...）正确解析。
run_py() {
    PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}" python3 "$@"
}

# ---------------------------------------------------------------------------
# 1. 记录触发回滚的失败项与读取回滚目标（R9.3）
# ---------------------------------------------------------------------------
log "回滚已触发。触发失败项 (ROLLBACK_REASON): ${ROLLBACK_REASON}"
log "部署根目录 APP_DIR=${APP_DIR}，状态文件=${STATE_FILE}"

LAST_STABLE_TAG="$(run_py -c '
import sys
from lib.stable_tag import read_stable_tag
value = read_stable_tag(sys.argv[1])
sys.stdout.write("" if value is None else value)
' "$STATE_FILE")"

# ---------------------------------------------------------------------------
# 2. 判定是否存在可回滚版本（R7.3 / R9.4）
# ---------------------------------------------------------------------------
if ! run_py -c '
import sys
from lib.stable_tag import decide_rollback
last = sys.argv[1] if sys.argv[1] else None
sys.exit(0 if decide_rollback(last) else 1)
' "$LAST_STABLE_TAG"; then
    log "无可回滚版本：Last_Stable_Tag 不存在、为空或非法（首次部署或状态缺失）。"
    log "跳过回滚，流水线以失败收场。触发失败项: ${ROLLBACK_REASON}"
    exit "${EXIT_SKIP_NO_TARGET}"
fi

log "回滚目标 SHA (Last_Stable_Tag): ${LAST_STABLE_TAG}"

# ---------------------------------------------------------------------------
# 3. 以 Last_Stable_Tag 作为 IMAGE_TAG 重部署 backend/worker/web（R7.1）
# ---------------------------------------------------------------------------
if ! cd "${APP_DIR}"; then
    log "无法进入部署目录 ${APP_DIR}，回滚失败需人工介入。"
    exit "${EXIT_MANUAL_INTERVENTION}"
fi

# 导出 IMAGE_TAG 供 compose 变量插值；shell 环境变量优先于 --env-file 中的同名值。
export IMAGE_TAG="${LAST_STABLE_TAG}"

log "拉取回滚目标镜像 (IMAGE_TAG=${IMAGE_TAG}) ..."
if ! docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" pull backend worker web; then
    log "回滚镜像拉取失败，回滚失败需人工介入，保留当前状态。"
    exit "${EXIT_MANUAL_INTERVENTION}"
fi

log "以回滚目标镜像重启 backend/worker/web ..."
if ! docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d backend worker web; then
    log "回滚服务重启失败，回滚失败需人工介入，保留当前状态。"
    exit "${EXIT_MANUAL_INTERVENTION}"
fi

# ---------------------------------------------------------------------------
# 4. 回滚后 Health_Check（R7.2）：最多 5 次、间隔 10s、单次超时 10s、窗口 60s
# ---------------------------------------------------------------------------
log "回滚后健康检查开始：${HEALTH_URL}（最多 ${HEALTH_MAX_ATTEMPTS} 次、间隔 ${HEALTH_INTERVAL_S}s）"

declare -a HEALTH_OUTCOMES=()
attempt=1
while [ "${attempt}" -le "${HEALTH_MAX_ATTEMPTS}" ]; do
    if curl -fsS --max-time "${HEALTH_TIMEOUT_S}" "${HEALTH_URL}" >/dev/null 2>&1; then
        log "健康检查第 ${attempt}/${HEALTH_MAX_ATTEMPTS} 次：成功"
        HEALTH_OUTCOMES+=("true")
        break
    fi
    log "健康检查第 ${attempt}/${HEALTH_MAX_ATTEMPTS} 次：失败"
    HEALTH_OUTCOMES+=("false")
    if [ "${attempt}" -lt "${HEALTH_MAX_ATTEMPTS}" ]; then
        sleep "${HEALTH_INTERVAL_S}"
    fi
    attempt=$((attempt + 1))
done

# 复用 lib.retry::retry_succeeds 与 RetryConfig(5, 10, 10, 60) 做最终判定（R7.2）。
if run_py -c '
import sys
from lib.retry import RetryConfig, retry_succeeds
outcomes = [token == "true" for token in sys.argv[1:]]
cfg = RetryConfig(max_retries=5, interval_s=10, timeout_s=10, window_s=60)
sys.exit(0 if retry_succeeds(outcomes, cfg) else 1)
' "${HEALTH_OUTCOMES[@]}"; then
    # R7.4：回滚后健康检查成功 → 流水线以失败结束并报告「已回滚到 <SHA>」。
    log "回滚后健康检查通过。已回滚到 ${LAST_STABLE_TAG}（触发失败项: ${ROLLBACK_REASON}）。"
    log "流水线本次运行整体判定为失败（回滚成功不改变失败结论）。"
    exit "${EXIT_ROLLED_BACK}"
else
    # R7.5：回滚后健康检查失败 → 流水线以失败结束、需人工介入、保留当前状态。
    log "回滚后健康检查在窗口内未通过。回滚失败需人工介入，保留当前状态。"
    log "回滚目标 SHA: ${LAST_STABLE_TAG}，触发失败项: ${ROLLBACK_REASON}。"
    exit "${EXIT_MANUAL_INTERVENTION}"
fi
