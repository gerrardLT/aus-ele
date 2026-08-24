# CI/CD 部署与回滚说明

本文档说明 `aus-ele` 项目的持续集成 / 持续交付（CI/CD）流水线设计、所需配置、生产服务器前置准备，以及部署后验证与失败自动回滚机制。

---

## 1. 权威 Python 版本：3.11

项目统一以 **Python 3.11** 为唯一权威版本，三处必须保持一致：

| 位置 | 配置 | 说明 |
|------|------|------|
| CI 流水线 | `.github/workflows/ci.yml` 中 `PYTHON_VERSION: "3.11"` | `backend` 作业 `setup-python` 使用该版本 |
| 后端镜像 | `Dockerfile.backend` 中 `FROM python:3.11-slim` | 生产运行时镜像基础版本 |
| 本地开发 | 本地虚拟环境（venv）使用 Python 3.11 | 与 CI / 镜像对齐，避免「本地能跑、CI 失败」 |

> 升级 Python 版本时，必须同步更新以上三处，否则视为破坏权威版本一致性。

---

## 2. CI/CD 流水线总览

流水线由 **6 个作业（Job）** 组成，分为 CI 质量门与 CD 交付两阶段，通过 `needs:` 建立依赖、通过 `if:` 控制 CD 仅在 `main` 分支 push 时触发。

```
backend ─┐
         ├─> build-push ──> deploy ──> verify
frontend ┘                     │          │
                               └──(failure)┴──> rollback（失败时）
```

| 作业 | 阶段 | 触发条件 | 说明 |
|------|------|---------|------|
| `backend` | CI | push/PR to main/develop | mypy 类型检查 + 单元/集成测试 |
| `frontend` | CI | push/PR to main/develop | ESLint + 前端测试 + build 验证 |
| `build-push` | CD | main push | 构建 backend/web 镜像并推送 GHCR（latest + SHA） |
| `deploy` | CD | build-push 成功后 | SSH 远程拉取 SHA 镜像并重启 |
| `verify` | CD | deploy 成功后 | Health Check（10 次/5s）+ Smoke Test |
| `rollback` | CD | deploy 或 verify 失败 | 回滚到 Last_Stable_Tag |

---

## 3. 触发条件

```yaml
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]
```

- CI 质量门（backend + frontend）：push 或 PR 到 main/develop 时触发
- CD 交付（build-push → deploy → verify）：仅 main 分支 push 时触发

---

## 4. 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PYTHON_VERSION` | `3.11` | Python 版本 |
| `NODE_VERSION` | `20` | Node.js 版本 |
| `REGISTRY` | `ghcr.io` | 容器镜像仓库 |
| `APP_DIR` | `/www/wwwroot/aus-ele` | 生产服务器项目目录 |
| `API_HOST_PORT` | `18085` | 后端 API 宿主机端口 |
| `WEB_HOST_PORT` | `18080` | 前端 Web 宿主机端口 |

---

## 5. 必需的 GitHub Secrets

在仓库 Settings → Secrets and variables → Actions 中配置：

| Secret | 必需 | 说明 |
|--------|------|------|
| `SSH_HOST` | 是 | 生产服务器主机名/IP |
| `SSH_USER` | 是 | SSH 登录用户名 |
| `SSH_KEY` | 是 | SSH 私钥（PEM 格式） |
| `SSH_PORT` | 否 | SSH 端口（缺省 22） |
| `AUS_ELE_JWT_SECRET` | 是 | 后端 JWT 密钥 |
| `FINGRID_API_KEY` | 是 | Fingrid API Key |
| `AUS_ELE_PG_PASSWORD` | 否 | PostgreSQL 密码（缺省 `aemo_pg_pass_2026`） |

> GHCR 登录复用内置 `GITHUB_TOKEN`（packages: write），无需额外 Secret。

---

## 6. 各作业详细说明

### 6.1 backend（CI 后端质量门）

1. `actions/checkout@v4`
2. `actions/setup-python@v5`（Python 3.11，pip 缓存）
3. `pip install -r requirements.txt` + `mypy hypothesis pytest pytest-benchmark`
4. `mypy backend/`（类型检查，当前非阻断）
5. `python -m unittest discover -s tests`（单元测试，当前非阻断）
6. 集成测试（当前非阻断）

### 6.2 frontend（CI 前端质量门）

1. `actions/checkout@v4`
2. `actions/setup-node@v4`（Node 20，npm 缓存）
3. `npm ci --no-audit --no-fund`
4. `npm run lint`（ESLint）
5. `node --test src/lib/*.test.js`（前端测试，2026-08-20 起为阻断门禁，失败即阻断 frontend job 及下游 build-push/CD 链）
   - 双 runner 边界（2026-08-24 收口）：`src/lib/*.test.js` = node:test；`src/test/` 与 `**/__tests__/` = vitest（`npm test`），禁止纳入 node --test
6. `npm test`（vitest 守卫，2026-08-24 新增，稳定期非阻断）
7. `npm run build`（构建验证）

### 6.3 build-push（构建并推送镜像）

- 条件：`needs: [backend, frontend]`，仅 main push
- 权限：`packages: write`
- 流程：
  1. 规范化 IMAGE_PREFIX 为小写（GHCR 要求）
  2. 登录 GHCR（复用 GITHUB_TOKEN）
  3. Preflight 不可变标签校验（SHA 标签已存在则拒绝覆盖）
  4. 构建并推送 backend + web 镜像（latest + 完整 SHA 双标签）
  5. 含重试机制：最多 3 次、每次间隔 ≥10s
  6. 使用 gha 缓存加速构建

### 6.4 deploy（远程部署）

- 条件：build-push 成功后
- 流程：
  1. 校验必需 Secret（缺失则立即失败，不输出 secret 值）
  2. SSH 连接性检查（30s 超时）
  3. 标记 `deploy_attempted`（回滚门控依据）
  4. SSH 执行 `deploy.sh`：写 `.env.prod`、登录 GHCR、pull 镜像、`up -d`
  5. 确认四服务 running（120s 窗口）

### 6.5 verify（部署后验证）

- 条件：deploy 成功后
- 流程：
  1. SSH 执行 `verify.sh`
  2. Health Check：10 次请求、间隔 5s、窗口 60s
  3. Smoke Test
  4. 通过后写入 Last_Stable_Tag

### 6.6 rollback（失败回滚）

- 条件：`failure() && deploy_attempted == 'true'`
- 仅当已开始变更（SSH 连接成功后）才触发回滚
- SSH 不可达时不回滚（服务未改动）
- 流程：
  1. 计算回滚原因（deploy 失败 vs verify 失败）
  2. SSH 执行 `rollback.sh`，回滚到 Last_Stable_Tag
  3. rollback.sh 总以非零退出 → 流水线整体判定为失败

---

## 7. 生产部署架构

生产环境使用 `docker-compose.prod.yml`，按 `IMAGE_TAG` 拉取 GHCR 预构建镜像（不在生产机本地构建）。

### 7.1 服务组成

| 服务 | 镜像 | 内存限制 | 端口映射 |
|------|------|---------|---------|
| `postgres` | `postgres:16-alpine` | 1024m | 15432:5432 |
| `backend` | GHCR 预构建 | 1200m | 18085:8085 |
| `worker` | GHCR 预构建 | 1536m | 无外部端口 |
| `web` | GHCR 预构建 | 384m | 18080:80 |
| `redis` | `redis:7-alpine` | 256m | 16379:6379 |

### 7.2 关键环境变量

| 变量 | 必需 | 缺省 |
|------|------|------|
| `AUS_ELE_PG_PASSWORD` | 是 | — |
| `AUS_ELE_JWT_SECRET` | 是 | — |
| `FINGRID_API_KEY` | 否 | 空 |
| `AUS_ELE_DB_BACKEND` | 是 | `postgresql` |
| `AUS_ELE_ENABLE_SCHEDULER` | 否 | `false`（worker 中为 `true`） |
| `AUS_ELE_ENABLE_JOB_WORKER` | 否 | `false`（worker 中为 `true`） |

### 7.3 数据卷

| 卷名 | 用途 |
|------|------|
| `pg_data` | PostgreSQL 数据持久化 |
| `redis_data` | Redis AOF 持久化 |
| `./data` | SQLite 数据库 / 数据文件 |
| `./logs` | 应用日志 |
| `./reports` | 报告输出 |

---

## 8. 部署脚本

生产服务器 `${APP_DIR}/deploy/scripts/` 目录下：

| 脚本 | 说明 |
|------|------|
| `deploy.sh` | 写 `.env.prod`、登录 GHCR、pull 镜像、up -d |
| `verify.sh` | Health Check + Smoke Test |
| `rollback.sh` | 回滚到 Last_Stable_Tag |

---

## 9. 前端生产构建

前端镜像在 CI 中构建，生产运行时为 Nginx 静态文件服务。

构建参数：
- `VITE_API_BASE`：API 基础路径（缺省 `/api`）

---

## 10. 回滚策略

| 场景 | deploy_attempted | 回滚行为 |
|------|-----------------|---------|
| SSH 不可达（服务器宕机/网络故障） | 未设置 | 不回滚（服务未改动） |
| 镜像拉取失败 / 服务未 running | true | 回滚到 Last_Stable_Tag |
| Health Check 失败 | true | 回滚到 Last_Stable_Tag |
| Smoke Test 失败 | true | 回滚到 Last_Stable_Tag |
