# Implementation Plan: CI/CD 流水线

## Overview

本实施计划将设计文档转化为一系列增量式编码任务。整体策略遵循 TDD：先构建可被属性测试覆盖的服务器侧纯函数库（`deploy/scripts/lib/*.py`），每个模块紧随其对应的属性测试（1:1 映射设计中的 9 条 Correctness Properties）；随后封装薄 shell 脚本（deploy/verify/rollback），再新增生产编排文件 `docker-compose.prod.yml`，接着改造 `.github/workflows/ci.yml` 补全 CD 作业与门控，再改造 `smoke_test_api.py` 支持环境变量覆盖与退出码，最后对齐 `.env.docker.example` 与文档。

编排层（GitHub Actions YAML、SSH、docker pull/up、GHCR 推送、日志屏蔽）不做属性测试，由集成测试与冒烟/配置检查覆盖。

约定：测试与调试文件置于 `test/` 目录，文档置于 `docs/` 目录（遵循工作区规则）。属性测试使用 `hypothesis`，每个 `@settings(max_examples=100)`，并以 `# Feature: cicd-pipeline, Property {number}: {property_text}` 注释标注。

## Tasks

- [x] 1. 搭建服务器侧脚本目录与纯函数库骨架
  - 创建 `deploy/scripts/` 与 `deploy/scripts/lib/` 目录结构
  - 创建 `deploy/scripts/lib/__init__.py`，使 lib 成为可导入包
  - 定义共享数据结构 `RetryConfig`（`max_retries, interval_s, timeout_s, window_s`）于 `deploy/scripts/lib/retry.py`，供后续重试判定复用
  - 确认 `test/` 目录存在，作为属性测试与单元测试的放置位置
  - _Requirements: 6.1, 7.2_

- [x] 2. 实现校验库 `validate.py`（SHA 校验 + Secret 校验）
  - [x] 2.1 实现 `is_valid_sha` 与镜像标签生成
    - 在 `deploy/scripts/lib/validate.py` 中实现 `is_valid_sha(s)`：当且仅当 `s` 恰为 40 位小写十六进制字符时返回真
    - 实现由合法 SHA 生成不可变镜像标签的纯函数（标签完整包含该 40 位 SHA）
    - _Requirements: 3.2_

  - [x]* 2.2 编写 `is_valid_sha` / 标签生成的属性测试
    - **Property 1: Commit SHA 标签校验**
    - **Validates: Requirements 3.2**
    - 置于 `test/`，使用 hypothesis `@settings(max_examples=100)`

  - [x] 2.3 实现 `validate_secrets`
    - 在 `deploy/scripts/lib/validate.py` 中实现 `validate_secrets(mapping, required)`：当且仅当 `required` 中每个名称在 `mapping` 中存在且值为非空字符串时通过
    - 校验失败时返回的报告恰好列出所有缺失/为空的名称，且报告中不包含任何 secret 的值
    - _Requirements: 5.5_

  - [x]* 2.4 编写 `validate_secrets` 的属性测试
    - **Property 6: 必需 Secret 校验**
    - **Validates: Requirements 5.5**
    - 置于 `test/`，使用 hypothesis `@settings(max_examples=100)`

- [x] 3. 实现重试与服务状态库 `retry.py`
  - [x] 3.1 实现 `retry_succeeds`
    - 在 `deploy/scripts/lib/retry.py` 中实现 `retry_succeeds(outcomes, cfg)`：当且仅当前 `max_retries` 次尝试内至少出现一次成功时返回成功；实际尝试次数恒 `≤ max_retries`，且首次成功后停止
    - _Requirements: 6.1, 6.3, 7.2, 3.8_

  - [x]* 3.2 编写 `retry_succeeds` 的属性测试
    - **Property 3: 通用重试判定语义**
    - **Validates: Requirements 6.1, 6.3, 7.2, 3.8**
    - 以多组 RetryConfig 覆盖部署后健康检查（10/5）、回滚后健康检查（5/10）与推送重试（3 次）
    - 置于 `test/`，使用 hypothesis `@settings(max_examples=100)`

  - [x] 3.3 实现 `services_all_running`
    - 在 `deploy/scripts/lib/retry.py` 中实现 `services_all_running(ps, required)`：当且仅当 `required`（backend、worker、web、redis）中每个服务在 `ps` 中状态均为 running 时为真
    - _Requirements: 4.3_

  - [x]* 3.4 编写 `services_all_running` 的属性测试
    - **Property 7: 服务运行状态确认**
    - **Validates: Requirements 4.3**
    - 置于 `test/`，使用 hypothesis `@settings(max_examples=100)`

- [x] 4. 实现冒烟评估与推送决策库 `smoke.py`
  - [x] 4.1 实现 `evaluate_smoke`
    - 在 `deploy/scripts/lib/smoke.py` 中实现 `evaluate_smoke(results)`：当且仅当不存在任何返回 500 的端点且不存在任何连接失败的端点时判定通过；否则失败
    - _Requirements: 6.2, 6.4_

  - [x]* 4.2 编写 `evaluate_smoke` 的属性测试
    - **Property 4: Smoke_Test 结果评估**
    - **Validates: Requirements 6.2, 6.4**
    - 置于 `test/`，使用 hypothesis `@settings(max_examples=100)`

  - [x] 4.3 实现 `decide_push`
    - 在 `deploy/scripts/lib/smoke.py` 中实现 `decide_push(existing, tag)`：当且仅当 `tag` 不在 `existing` 中时允许推送；`tag` 已存在则一律拒绝（不覆盖）
    - _Requirements: 3.6_

  - [x]* 4.4 编写 `decide_push` 的属性测试
    - **Property 2: 不可变标签覆盖保护**
    - **Validates: Requirements 3.6**
    - 置于 `test/`，使用 hypothesis `@settings(max_examples=100)`

- [x] 5. 实现稳定标签与回滚决策库 `stable_tag.py`
  - [x] 5.1 实现 `write_stable_tag` / `read_stable_tag`
    - 在 `deploy/scripts/lib/stable_tag.py` 中实现读写 Last_Stable_Tag（单行 40 位 commit SHA）的纯函数，支持注入路径以便测试用 tmp 路径
    - 满足 round-trip：先写后读返回值与写入值相等
    - _Requirements: 6.5, 7.1_

  - [x]* 5.2 编写 `write/read_stable_tag` 往返的属性测试
    - **Property 5: Last_Stable_Tag 持久化往返**
    - **Validates: Requirements 6.5, 7.1**
    - 使用 tmp 路径，置于 `test/`，使用 hypothesis `@settings(max_examples=100)`

  - [x] 5.3 实现 `decide_rollback`
    - 在 `deploy/scripts/lib/stable_tag.py` 中实现 `decide_rollback(last_stable)`：当且仅当存在合法 Last_Stable_Tag 时决定执行回滚；不存在/为空/非法则决定跳过并以失败收场
    - _Requirements: 7.3_

  - [x]* 5.4 编写 `decide_rollback` 的属性测试
    - **Property 8: 回滚目标决策**
    - **Validates: Requirements 7.3**
    - 置于 `test/`，使用 hypothesis `@settings(max_examples=100)`

- [x] 6. 实现阶段状态归类库 `status.py`
  - [x] 6.1 实现 `classify_stage`
    - 在 `deploy/scripts/lib/status.py` 中实现 `classify_stage(outcome)`：确定性地恰好返回 `成功 / 失败 / 跳过` 三种取值之一
    - _Requirements: 9.2_

  - [x]* 6.2 编写 `classify_stage` 的属性测试
    - **Property 9: 阶段状态归类**
    - **Validates: Requirements 9.2**
    - 置于 `test/`，使用 hypothesis `@settings(max_examples=100)`

- [x] 7. Checkpoint - 确保纯函数库与全部属性测试通过
  - 确保 9 个属性测试与相关单元/边界测试全部通过，如有疑问询问用户。

- [x] 8. 实现服务器侧 shell 封装脚本
  - [x] 8.1 实现 `deploy/scripts/deploy.sh`
    - 写 `/opt/aus-ele/.env.prod`（chmod 600，含密钥与 `IMAGE_TAG`）、`git fetch && git checkout <SHA>`、`docker login`、`compose -f docker-compose.prod.yml --env-file .env.prod pull`（300s 超时）、`up -d`
    - 调用 `lib/retry.py::services_all_running` 在 120s 内轮询确认 backend/worker/web/redis 进入 running
    - 部署开始拉取/重启即输出 `deploy_attempted=true`
    - _Requirements: 4.2, 4.3, 5.2, 4.5_

  - [x] 8.2 实现 `deploy/scripts/verify.sh`
    - 对 `/api/health` 执行 Health_Check（单次 10s、最多 10 次、间隔 5s、窗口 60s），调用 `lib/retry.py::retry_succeeds`
    - Health 成功后运行 `smoke_test_api.py`，以其退出码经 `lib/smoke.py::evaluate_smoke` 语义判定
    - 验证通过后调用 `lib/stable_tag.py::write_stable_tag` 写入本次 SHA
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 8.3_

  - [x] 8.3 实现 `deploy/scripts/rollback.sh`
    - 调用 `lib/stable_tag.py::read_stable_tag` 与 `decide_rollback`：无可回滚版本则跳过并以失败结束并报告原因
    - 存在则以 Last_Stable_Tag 为 `IMAGE_TAG` 重部署 backend/worker/web，回滚后 Health_Check（最多 5 次、间隔 10s、窗口 60s）
    - 记录触发回滚的失败项与回滚目标 SHA
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 9.3, 9.4_

  - [x]* 8.4 编写 shell 脚本与 lib 集成的烟测/集成测试
    - 验证 deploy/verify/rollback 正确调用 lib 纯函数并传播退出码
    - _Requirements: 4.3, 6.5, 7.1_

- [x] 9. 新增生产编排文件 `docker-compose.prod.yml`
  - 创建仓库根目录 `docker-compose.prod.yml`，backend/worker/web 改为 `image: ${REGISTRY:-ghcr.io}/${IMAGE_PREFIX}/<svc>:${IMAGE_TAG}`，移除 `build:` 与源码挂载，保留数据卷与运行时环境变量占位
    - backend 注入 `AUS_ELE_JWT_SECRET:?required`、`FINGRID_API_KEY`，端口 `${API_HOST_PORT:-18085}:8085`
    - web 端口 `${WEB_HOST_PORT:-18080}:80`，redis 使用 `redis:7-alpine` 与 `redis_data` 卷
  - _Requirements: 4.3, 5.2, 7.1_

- [x] 10. 改造 `.github/workflows/ci.yml`：修复 CI 弱点
  - [x] 10.1 修复 frontend 作业并对齐 Python 版本
    - 移除前端测试的 `|| true`，使测试失败真实传播；确认 lint 不使用 `--max-warnings=0`；构建失败/无产物即作业失败
    - 确认 backend 作业 `PYTHON_VERSION: "3.11"` 与 `Dockerfile.backend` 对齐
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 8.1, 1.5, 8.2_

  - [x]* 10.2 编写 Python 版本对齐与触发矩阵的配置检查
    - 校验 `setup-python` 版本与 `FROM python:3.11-slim` 一致；push/PR 触发 CI、main-push 才触发 CD
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 4.6, 8.2_

- [x] 11. 改造 `.github/workflows/ci.yml`：新增 CD 作业
  - [x] 11.1 增强 `build-push` 作业
    - 每镜像同时打 `latest` 与完整 40 位 `${{ github.sha }}` 标签；`needs: [backend, frontend]` 且 `if` 限定 main-push
    - 新增 preflight 步骤调用 `lib/smoke.py::decide_push` 检查 SHA 标签是否已存在，存在则失败不覆盖
    - 推送步骤包裹重试（最多 3 次、间隔 ≥10s）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [x] 11.2 新增 `deploy` 作业
    - `needs: [build-push]` 继承 main-push 条件；首步在 runner 上调用 `lib/validate.py::validate_secrets` 校验必需 Secret，缺失则在任何 SSH/拉取/重启前失败
    - 使用 `appleboy/ssh-action`（连接超时 30s、最多 3 次）经 `envs:` 注入密钥与 `IMAGE_TAG`，执行 `deploy/scripts/deploy.sh`
    - 输出 `deploy_attempted`、`image_tag`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 5.1, 5.2, 5.5_

  - [x] 11.3 新增 `verify` 作业
    - `needs: [deploy]`，经 SSH 执行 `deploy/scripts/verify.sh`，验证通过则写入 Last_Stable_Tag
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 8.3_

  - [x] 11.4 新增 `rollback` 作业
    - `needs: [deploy, verify]` 且 `if: failure() && needs.deploy.outputs.deploy_attempted == 'true'`，经 SSH 执行 `deploy/scripts/rollback.sh`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 11.5 实现各作业可观测性输出
    - 每个 Job 末尾向 `$GITHUB_STEP_SUMMARY` 写入 `成功/失败/跳过`（调用 `lib/status.py::classify_stage`）；失败步骤名与错误信息输出到日志；回滚触发项/目标 SHA/跳过原因写入日志
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 12. 改造 `smoke_test_api.py`
  - 将 `BASE` 改为可由 `SMOKE_BASE_URL` 环境变量覆盖，默认指向生产 `http://127.0.0.1:<API_HOST_PORT>`
  - 以进程退出码表达结论：存在任一 500 或连接失败则非零退出（与 `evaluate_smoke` 语义一致）
  - _Requirements: 6.2, 6.4, 8.3_

- [x] 13. 更新 `.env.docker.example` 与文档
  - 在 `.env.docker.example` 中补充 `REGISTRY`/`IMAGE_PREFIX`/`IMAGE_TAG`/`API_HOST_PORT`/`WEB_HOST_PORT` 占位
  - 确认 `.gitignore` 使 `.env*`（示例除外）不被追踪
  - 在 `docs/` 下记录 Python 3.11 权威版本与 CD 部署/回滚说明
  - _Requirements: 5.1, 5.4, 1.5, 8.2_

- [x] 14. Final checkpoint - 确保全部测试通过
  - 确保所有属性测试、单元/集成/配置检查通过，如有疑问询问用户。

## Notes

- 标记 `*` 的子任务为可选（测试类），可为加速 MVP 跳过；核心实现任务不可标记可选。
- 9 个属性测试与设计中的 Property 1–9 一一对应，均使用 hypothesis 且 `@settings(max_examples=100)`，置于 `test/` 目录。
- 编排层（YAML/SSH/docker/GHCR）不做属性测试，由集成/冒烟/配置检查覆盖。
- 每个任务标注其实现的 Requirements 与（测试任务）Property 编号以便溯源。
- 测试/调试文件置于 `test/`，文档置于 `docs/`（遵循工作区规则）。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "2.3", "3.1", "3.3", "4.1", "4.3", "5.1", "5.3", "6.1"] },
    { "id": 2, "tasks": ["2.2", "2.4", "3.2", "3.4", "4.2", "4.4", "5.2", "5.4", "6.2"] },
    { "id": 3, "tasks": ["8.1", "8.2", "8.3", "9", "12"] },
    { "id": 4, "tasks": ["8.4", "10.1", "11.1"] },
    { "id": 5, "tasks": ["10.2", "11.2", "11.3", "11.4", "11.5"] },
    { "id": 6, "tasks": ["13"] }
  ]
}
```
