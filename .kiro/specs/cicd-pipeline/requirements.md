# Requirements Document

## Introduction

本文档定义 `aus-ele` 项目完整 CI/CD 流水线的需求。当前仓库已有 `.github/workflows/ci.yml`，其持续集成（CI）部分基本完整（后端 mypy 类型检查 + 单元/集成测试、前端 ESLint + 构建、在 main 分支构建并推送镜像到 GHCR），但持续交付（CD）部分缺失：流水线在推送镜像后即停止，没有真正的部署、部署后验证、回滚和密钥注入机制，同时 CI 存在若干已知弱点（前端测试使用 `|| true` 吞掉失败、CI 与生产运行时 Python 版本不一致、根目录 `smoke_test_api.py` 未接入流水线）。

本需求基于以下已确认的部署上下文：

- **部署目标**：自托管单机，通过 GitHub Actions 经 SSH 远程连接目标服务器，拉取 GHCR 镜像并用 docker-compose 重启服务。
- **环境分层**：当前仅有单一 production 环境（仅一台服务器）。
- **生产触发方式**：main 分支 push 后自动部署到生产，无需人工审批门控。
- **质量与安全要求**：部署后执行健康检查并接入 `smoke_test_api.py`；验证失败自动回滚到上一稳定镜像；密钥通过 GitHub Secrets 注入；修复现有 CI 弱点（前端测试硬性失败 + Python 版本对齐）。

本需求聚焦"做什么"（流水线应保证的行为与质量门），具体实现方式（脚本细节、Action 选择、compose 改造）留待设计阶段。

## Glossary

- **Pipeline**：定义在 GitHub Actions 中的完整 CI/CD 流水线，由若干 Stage 组成。
- **CI_Stage**：持续集成阶段，包含后端检查、前端检查与镜像构建推送。
- **CD_Stage**：持续交付阶段，将已构建镜像部署到生产服务器并完成部署后验证。
- **Backend_Check**：后端质量门，执行 mypy 类型检查与单元/集成测试。
- **Frontend_Check**：前端质量门，执行 ESLint、前端单元测试与生产构建。
- **Image_Builder**：构建后端与前端容器镜像并推送到 Container_Registry 的流水线组件。
- **Container_Registry**：容器镜像仓库，指 GitHub Container Registry（GHCR）。
- **Image_Tag**：镜像标签，包含可变标签 `latest` 与不可变的提交标签（commit SHA）。
- **Deployer**：CD_Stage 中通过 SSH 在 Production_Server 上执行部署动作的流水线组件。
- **Production_Server**：自托管目标服务器，运行 docker-compose 编排的 backend、worker、web、redis 服务。
- **Health_Check**：对已部署 backend 服务 `/api/health` 端点的可用性探测。
- **Smoke_Test**：部署后针对生产服务运行的 `smoke_test_api.py` 端点冒烟测试。
- **Post_Deploy_Verification**：部署后验证步骤，由 Health_Check 与 Smoke_Test 共同构成。
- **Rollback**：当 Post_Deploy_Verification 失败时，将服务恢复到上一已知稳定镜像版本的动作。
- **Last_Stable_Tag**：上一次通过 Post_Deploy_Verification 的镜像 commit SHA 标签。
- **Secret**：敏感凭证，包括 `AUS_ELE_JWT_SECRET`、`FINGRID_API_KEY`、SSH 部署凭证等，存储于 GitHub Secrets。
- **Runtime_Python_Version**：生产容器镜像（`Dockerfile.backend`）所使用的权威 Python 版本，当前为 3.11。
- **Pipeline_Operator**：触发或观察流水线运行的开发者。

## Requirements

### Requirement 1: 后端质量门

**User Story:** 作为开发者，我希望后端代码在合并和部署前通过类型检查与测试，以便保证后端质量。

#### Acceptance Criteria

1. WHEN 代码被 push 到 main 或 develop 分支，THE Backend_Check SHALL 完整执行 mypy 类型检查、单元测试与集成测试三类检查。
2. WHEN 针对 main 或 develop 分支创建 pull request，THE Backend_Check SHALL 完整执行 mypy 类型检查、单元测试与集成测试三类检查。
3. IF mypy 类型检查报告错误，THEN THE Backend_Check SHALL 以非零退出码的失败状态结束、报告失败的检查项并阻止后续 CD_Stage 执行。
4. IF 任一单元测试或集成测试失败，THEN THE Backend_Check SHALL 以非零退出码的失败状态结束、报告失败的检查项并阻止后续 CD_Stage 执行。
5. THE Backend_Check SHALL 使用版本号与 Runtime_Python_Version（当前为 3.11）一致的 Python 版本运行所有后端检查。
6. WHEN mypy 类型检查、单元测试与集成测试三类检查全部通过，THE Backend_Check SHALL 以成功状态结束并放行后续 CD_Stage。

### Requirement 2: 前端质量门

**User Story:** 作为开发者，我希望前端代码在合并和部署前通过代码规范、测试与构建验证，以便保证前端质量。

#### Acceptance Criteria

1. WHEN 代码被 push 到 main 或 develop 分支，THE Frontend_Check SHALL 运行 ESLint、前端单元测试与生产构建，且仅在三者全部成功时以成功状态结束。
2. WHEN 针对 main 或 develop 分支创建 pull request，THE Frontend_Check SHALL 运行 ESLint、前端单元测试与生产构建，且仅在三者全部成功时以成功状态结束。
3. IF 任一前端单元测试失败，THEN THE Frontend_Check SHALL 以非零退出码的失败状态结束并阻止后续 CD_Stage 执行。
4. IF ESLint 报告任一 error 级别（severity 为 error）的规则违规，THEN THE Frontend_Check SHALL 以失败状态结束并阻止后续 CD_Stage 执行。
5. WHEN ESLint 仅报告 warning 级别且不存在任何 error 级别的规则违规，THE Frontend_Check SHALL 将 ESLint 视为通过且不阻塞后续 CD_Stage。
6. IF 前端生产构建以非零退出码结束或未产出可部署的构建产物，THEN THE Frontend_Check SHALL 以失败状态结束并阻止后续 CD_Stage 执行。

### Requirement 3: 镜像构建与推送

**User Story:** 作为开发者，我希望流水线为每次生产发布构建可追溯的容器镜像并推送到镜像仓库，以便部署和回滚有明确的镜像来源。

#### Acceptance Criteria

1. WHEN 代码被 push 到 main 分支且 Backend_Check 与 Frontend_Check 均成功，THE Image_Builder SHALL 构建后端镜像与前端镜像。
2. WHEN Image_Builder 构建镜像，THE Image_Builder SHALL 为每个镜像同时打上 `latest` 可变标签与该次提交完整 40 位 commit SHA 的不可变标签。
3. WHEN Image_Builder 完成构建，THE Image_Builder SHALL 将每个镜像的 `latest` 标签与 commit SHA 标签分别推送到 Container_Registry。
4. IF Backend_Check 或 Frontend_Check 失败，THEN THE Image_Builder SHALL 不构建任何镜像。
5. WHEN Image_Builder 向 Container_Registry 认证，THE Image_Builder SHALL 使用流水线提供的仓库写入凭证完成认证。
6. IF Container_Registry 中已存在与本次 commit SHA 相同的不可变标签，THEN THE Image_Builder SHALL 拒绝覆盖该标签并以失败状态结束。
7. IF 镜像构建失败，THEN THE Image_Builder SHALL 以失败状态结束、报告失败的镜像并不执行任何推送。
8. IF 向 Container_Registry 推送镜像失败，THEN THE Image_Builder SHALL 在最多重试 3 次（每次间隔不少于 10 秒）后仍失败时以失败状态结束。
9. IF Image_Builder 向 Container_Registry 认证失败，THEN THE Image_Builder SHALL 以失败状态结束且不在日志中明文输出认证凭证。

### Requirement 4: 生产部署

**User Story:** 作为开发者，我希望镜像构建成功后流水线自动将其部署到生产服务器，以便发布无需手动操作。

#### Acceptance Criteria

1. WHEN Image_Builder 成功将镜像推送到 Container_Registry，THE Deployer SHALL 通过 SSH 连接到 Production_Server，单次连接超时为 30 秒。
2. WHEN Deployer 连接到 Production_Server，THE Deployer SHALL 在 300 秒内拉取该次提交 commit SHA 标签对应的后端镜像与前端镜像。
3. WHEN Deployer 完成镜像拉取，THE Deployer SHALL 使用 docker-compose 以新镜像重启 backend、worker、web 与 redis 服务，并在 120 秒内确认上述四个服务均进入运行（running）状态。
4. IF Deployer 在最多 3 次尝试（每次连接超时 30 秒）内均无法通过 SSH 连接 Production_Server，THEN THE Deployer SHALL 以失败状态结束、报告连接错误且不更改 Production_Server 上正在运行的服务。
5. IF 镜像拉取未在 300 秒内完成，或服务重启后未在 120 秒内确认四个服务均进入运行状态，THEN THE Deployer SHALL 以失败状态结束并触发 Rollback。
6. THE Deployer SHALL 仅在 main 分支的 push 事件中执行。

### Requirement 5: 密钥与凭证管理

**User Story:** 作为运维人员，我希望部署所需的密钥通过安全方式注入而不出现在代码或日志中，以便保护敏感凭证。

#### Acceptance Criteria

1. WHEN CD_Stage 开始执行，THE Pipeline SHALL 从 GitHub Secrets 读取 `AUS_ELE_JWT_SECRET`、`FINGRID_API_KEY` 与 SSH 部署凭证，且不将其值写入任何代码仓库追踪文件或运行器持久化磁盘文件。
2. WHEN Deployer 在 Production_Server 上重启服务，THE Deployer SHALL 仅通过服务运行时环境变量注入 `AUS_ELE_JWT_SECRET`、`FINGRID_API_KEY` 与 SSH 部署凭证。
3. THE Pipeline SHALL 在所有 Stage 的日志输出中以固定屏蔽标记替代任一 Secret 的明文值，使日志中不出现 Secret 明文。
4. THE Pipeline SHALL 确保代码仓库追踪的任何文件中均不包含任一 Secret 的明文值。
5. IF 任一必需 Secret（`AUS_ELE_JWT_SECRET`、`FINGRID_API_KEY` 或 SSH 部署凭证）在 CD_Stage 开始时缺失或为空字符串，THEN THE Deployer SHALL 在执行任何 SSH 连接、镜像拉取或服务重启之前以失败状态结束，并在日志中报告缺失的 Secret 名称而不输出其值。

### Requirement 6: 部署后验证

**User Story:** 作为开发者，我希望部署完成后自动验证生产服务可用，以便在发布失败时立即发现。

#### Acceptance Criteria

1. WHEN Deployer 完成服务重启，THE Post_Deploy_Verification SHALL 对 backend 服务的 `/api/health` 端点执行 Health_Check，其中单次探测请求超时为 10 秒，最多重试 10 次，每次重试间隔 5 秒，总超时窗口为 60 秒。
2. WHEN `/api/health` 端点在重试窗口内返回指示服务健康的成功响应，THE Post_Deploy_Verification SHALL 判定 Health_Check 成功并针对生产服务运行 Smoke_Test（`smoke_test_api.py`）。
3. IF Health_Check 在最多 10 次、每次间隔 5 秒的重试（总超时窗口 60 秒）内均未返回成功响应，THEN THE Post_Deploy_Verification SHALL 以失败状态结束并触发 Rollback。
4. IF Smoke_Test 报告任一被测端点返回 500 错误或发生连接失败，THEN THE Post_Deploy_Verification SHALL 以失败状态结束并触发 Rollback。
5. WHEN Health_Check 成功且 Smoke_Test 的所有被测端点均未返回 500 错误且无连接失败，THE Pipeline SHALL 将该次提交 commit SHA 标签记录为 Last_Stable_Tag。

### Requirement 7: 失败回滚

**User Story:** 作为开发者，我希望部署或验证失败时服务能自动恢复到上一稳定版本，以便降低生产中断时间。

#### Acceptance Criteria

1. WHEN Rollback 被触发，THE Deployer SHALL 在 Production_Server 上使用 docker-compose 以 Last_Stable_Tag commit SHA 标签对应的后端镜像与前端镜像重启 backend、worker 与 web 服务。
2. WHEN Rollback 完成重启，THE Deployer SHALL 对 backend 服务的 `/api/health` 端点执行 Health_Check 以确认恢复结果，其中最多重试 5 次、每次间隔 10 秒、总超时窗口为 60 秒。
3. IF 不存在 Last_Stable_Tag（首次部署），THEN THE Deployer SHALL 跳过 Rollback 并以失败状态结束并报告无可回滚版本。
4. WHEN 回滚后的 Health_Check 在重试窗口内成功，THE Pipeline SHALL 以失败状态结束并报告本次部署已回滚到 Last_Stable_Tag。
5. IF 回滚后的 Health_Check 在重试窗口内仍未成功，THEN THE Pipeline SHALL 以失败状态结束、报告回滚失败需人工介入并保留当前服务状态。

### Requirement 8: 修复现有 CI 弱点

**User Story:** 作为开发者，我希望修复现有流水线中掩盖问题的配置，以便测试结果真实可信。

#### Acceptance Criteria

1. IF 任一前端单元测试失败，THEN THE Frontend_Check SHALL 返回非零退出码并以失败状态结束，且不使用任何抑制或吞掉失败的机制（如 `|| true`）。
2. THE Backend_Check SHALL 使用版本号与 Runtime_Python_Version（当前为 3.11）完全一致的 Python 解释器运行所有后端检查，使 CI、生产容器镜像与本地开发环境对齐到同一权威 Python 版本。
3. WHEN CD_Stage 执行 Post_Deploy_Verification，THE Pipeline SHALL 将 `smoke_test_api.py` 作为 Smoke_Test 运行。

### Requirement 9: 流水线可观测性

**User Story:** 作为开发者，我希望清楚地看到流水线每个阶段的结果，以便快速定位失败原因。

#### Acceptance Criteria

1. IF 任一 Stage 失败，THEN THE Pipeline SHALL 在该 Stage 的日志中输出导致失败的步骤名称与错误信息，且该日志对 Pipeline_Operator 可查阅并保留不少于 30 天。
2. WHEN Pipeline 运行结束，THE Pipeline SHALL 在运行摘要中以「成功 / 失败 / 跳过」三种取值之一标识每个 Stage 的状态。
3. WHEN Rollback 被触发，THE Pipeline SHALL 在日志中记录触发 Rollback 的失败项（Health_Check 或 Smoke_Test）与回滚到的 Last_Stable_Tag 值。
4. WHEN 因不存在 Last_Stable_Tag 而跳过 Rollback，THE Pipeline SHALL 在日志中记录 Rollback 被跳过及其原因（无可回滚版本）。
5. WHEN Pipeline 运行结束，THE Pipeline SHALL 在运行摘要中输出本次流水线的整体结论（成功或失败）。
