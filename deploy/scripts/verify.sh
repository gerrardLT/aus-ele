#!/usr/bin/env bash
#
# verify.sh — 部署后验证（Post_Deploy_Verification）
#
# 职责（对应 design.md Components 4 与 R6 / R8.3）：
#   1. Health_Check：对 http://127.0.0.1:<API_HOST_PORT>/api/health 探测，
#      单次超时 10s、最多 10 次、间隔 5s、总窗口 60s（R6.1）。
#      最终成败由 lib/retry.py::retry_succeeds + RetryConfig(10,5,10,60) 判定。
#   2. Smoke_Test：Health 成功后执行根目录 smoke_test_api.py（R6.2 / R8.3），
#      通过 SMOKE_BASE_URL 指向生产地址，以其进程退出码判定（R6.4）。
#   3. 验证通过 → 调用 lib/stable_tag.py::write_stable_tag 将本次 SHA 写入
#      <APP_DIR>/state/last_stable_tag（R6.5）。
#
# 失败语义（Fail-Fast）：
#   - Health 失败（R6.3）或 Smoke 失败（R6.4）→ 脚本以非零退出，触发上层 rollback。
#
# 可配置环境变量：
#   APP_DIR        部署仓库根目录（含 smoke_test_api.py 与 state/），默认 /www/wwwroot/aus-ele
#   API_HOST_PORT  后端宿主机映射端口，默认 18085
#   IMAGE_TAG      本次部署的 commit SHA；验证通过后写入 Last_Stable_Tag
#   WARMUP_S       Health 通过后等待容器完全就绪的秒数，默认 10
#
set -euo pipefail

# ---- 配置 ---------------------------------------------------------------
APP_DIR="${APP_DIR:-/www/wwwroot/aus-ele}"
API_HOST_PORT="${API_HOST_PORT:-18085}"
IMAGE_TAG="${IMAGE_TAG:-}"

# 本脚本所在目录即 deploy/scripts，其下的 lib 为可导入纯函数包。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HEALTH_URL="http://127.0.0.1:${API_HOST_PORT}/api/health"

# RetryConfig(max_retries=10, interval_s=5, timeout_s=10, window_s=60) —— R6.1
readonly MAX_RETRIES=10
readonly INTERVAL_S=5
readonly TIMEOUT_S=10
readonly WINDOW_S=60

log() { printf '[verify] %s\n' "$*"; }

# ---- Phase 1: Health_Check ---------------------------------------------
# 在总窗口内按配置探测 /api/health，将每次结果（True/False）收集为序列，
# 最终交由 lib/retry.py::retry_succeeds 依据 RetryConfig 做成败决策。
run_health_check() {
  log "Phase 1: Health_Check -> ${HEALTH_URL} (max ${MAX_RETRIES} attempts, interval ${INTERVAL_S}s, window ${WINDOW_S}s)"

  local outcomes=()
  local start_ts now elapsed attempt http_code
  start_ts=$(date +%s)

  for (( attempt=1; attempt<=MAX_RETRIES; attempt++ )); do
    now=$(date +%s); elapsed=$(( now - start_ts ))
    if (( elapsed >= WINDOW_S )); then
      log "  total window ${WINDOW_S}s exceeded after ${attempt} probe(s); stopping"
      break
    fi

    # 单次探测超时 10s；curl 失败（连接错误等）记为 HTTP 000。
    http_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time "${TIMEOUT_S}" "${HEALTH_URL}" || echo "000")

    if [[ "${http_code}" =~ ^2[0-9][0-9]$ ]]; then
      log "  attempt ${attempt}/${MAX_RETRIES}: HTTP ${http_code} -> healthy"
      outcomes+=("True")
      break
    fi

    log "  attempt ${attempt}/${MAX_RETRIES}: HTTP ${http_code} -> not healthy"
    outcomes+=("False")

    # 仅在仍有下一次尝试且不会越过总窗口时才间隔等待。
    if (( attempt < MAX_RETRIES )); then
      now=$(date +%s); elapsed=$(( now - start_ts ))
      if (( elapsed + INTERVAL_S < WINDOW_S )); then
        sleep "${INTERVAL_S}"
      fi
    fi
  done

  # 决策交由 lib 纯函数 retry_succeeds（保持与设计 Property 3 一致的语义）。
  local outcomes_csv
  outcomes_csv=$(IFS=,; echo "${outcomes[*]:-}")
  PYTHONPATH="${SCRIPT_DIR}" python3 -c '
import sys
from lib.retry import RetryConfig, retry_succeeds

raw = sys.argv[1]
outcomes = [tok == "True" for tok in raw.split(",") if tok != ""]
cfg = RetryConfig(max_retries=10, interval_s=5, timeout_s=10, window_s=60)
sys.exit(0 if retry_succeeds(outcomes, cfg) else 1)
' "${outcomes_csv}"
}

# ---- Phase 2: Smoke_Test -----------------------------------------------
# 执行根目录 smoke_test_api.py，BASE 由 SMOKE_BASE_URL 指向生产地址。
# 脚本以退出码表达结论（任一 500 / 连接失败 → 非零，见 task 12）。
run_smoke_test() {
  local smoke_script="${APP_DIR}/smoke_test_api.py"
  local base_url="http://127.0.0.1:${API_HOST_PORT}"
  log "Phase 2: Smoke_Test -> ${smoke_script} (SMOKE_BASE_URL=${base_url})"

  if [[ ! -f "${smoke_script}" ]]; then
    log "  smoke test script not found: ${smoke_script}"
    return 1
  fi

  SMOKE_BASE_URL="${base_url}" python3 "${smoke_script}"
}

# ---- Phase 3: 记录 Last_Stable_Tag -------------------------------------
record_stable_tag() {
  local state_file="${APP_DIR}/state/last_stable_tag"
  log "Phase 3: record Last_Stable_Tag -> ${state_file} (tag=${IMAGE_TAG})"

  PYTHONPATH="${SCRIPT_DIR}" APP_DIR="${APP_DIR}" IMAGE_TAG="${IMAGE_TAG}" python3 -c '
import os
from lib.stable_tag import write_stable_tag

tag = os.environ.get("IMAGE_TAG", "").strip()
if not tag:
    raise SystemExit("IMAGE_TAG is empty; cannot record Last_Stable_Tag")

state_path = os.path.join(os.environ["APP_DIR"], "state", "last_stable_tag")
write_stable_tag(tag, state_path)
print(f"[verify] recorded Last_Stable_Tag: {tag}")
'
}

# ---- 主流程 -------------------------------------------------------------
main() {
  log "starting post-deploy verification (APP_DIR=${APP_DIR}, API_HOST_PORT=${API_HOST_PORT})"

  if ! run_health_check; then
    log "RESULT: Health_Check FAILED within ${WINDOW_S}s window -> verification failed (R6.3, will trigger rollback)"
    exit 1
  fi
  log "Health_Check passed"

  # --- Warmup: 等待容器完全就绪（gunicorn worker 初始化、连接池预热等）---
  local warmup="${WARMUP_S:-10}"
  if (( warmup > 0 )); then
    log "Warmup: waiting ${warmup}s for container to fully stabilize before smoke test"
    sleep "${warmup}"
  fi

  if ! run_smoke_test; then
    log "RESULT: Smoke_Test FAILED (500 / connection failure) -> verification failed (R6.4, will trigger rollback)"
    exit 1
  fi
  log "Smoke_Test passed"

  record_stable_tag
  log "RESULT: post-deploy verification PASSED"
}

main "$@"
