> 状态：当前主工作台 QA 执行文档
>
> 范围说明：
> - 本文当前主要覆盖主工作台、AEMO/NEM/WEM 相关 API、同步脚本与现有自动化测试入口。
> - Fingrid 独立页面与 `/api/fingrid/*` 路由尚未在本文中系统展开，后续应补充专门章节。
> - Docker / 宝塔部署请参考 `docs/deployment/baota-docker.md`，不要把部署说明和 QA 执行说明混用。
> - 当前真实同步入口为 `/api/sync_data`；若正文中出现更旧的同步命名，应以实际代码为准。

# QA测试执行文档

> 文档定位：面向开发与测试协作执行  
> 文档范围：严格基于当前仓库现状  
> 最后更新：2026-04-22

## 1. 文档目标与适用范围

本文件用于指导当前仓库的测试执行，服务对象为开发人员、测试人员以及参与联调和发布验收的协作成员。

本文档的目标是：

- 说明当前仓库的测试对象和边界
- 提供可直接执行的环境准备与测试步骤
- 记录当前自动化测试现状及其限制
- 提供发布前回归清单、缺陷等级和验收标准

本文档不用于：

- 管理汇报
- 性能、安全、渗透等专项测试设计
- 完整浏览器兼容矩阵设计
- 与当前仓库实现无关的流程制度说明

## 2. 项目测试对象说明

当前仓库的测试对象可分为以下四层：

### 2.1 前端工作台

- 顶部导航与同步按钮
- 年份、区域、月份、季度、日类型筛选
- 价格趋势图与概要统计
- 事件叠加与事件说明
- 电网预测模块
- 峰谷套利分析
- FCAS 分析
- BESS 模拟
- 收入叠加
- 充电窗口
- 循环成本
- 投资分析

### 2.2 后端 API

- 元数据接口：`/api/years`、`/api/summary`、`/api/network-fees`
- 核心分析接口：`/api/price-trend`、`/api/event-overlays`、`/api/grid-forecast`、`/api/grid-forecast/coverage`
- 分析计算接口：`/api/peak-analysis`、`/api/hourly-price-profile`、`/api/fcas-analysis`、`/api/investment-analysis`
- 同步接口：`/api/sync_data`

### 2.3 数据采集与脚本

- `aemo_nem_scraper.py`
- `aemo_wem_scraper.py`
- `aemo_wem_ess_scraper.py`
- `aemo_grid_event_scraper.py`
- `scripts/init_wem_history.py`

### 2.4 自动化测试资产

- Python `unittest`
- 前端 `node:test`
- 前端构建与 lint 检查

## 3. 测试环境与前置条件

### 3.1 基础环境

| 项目 | 当前要求 | 说明 |
| --- | --- | --- |
| Python | 本机可执行 `python` | 后端、脚本、`unittest` 依赖 |
| Node.js | 本机可执行 `node` | 前端构建与 `node:test` 依赖 |
| npm | 本机可执行 `npm` | 前端依赖安装 |
| SQLite | 无需单独安装服务 | 本项目通过 Python `sqlite3` 直接访问 |
| Redis | 非强制，但建议准备 | 响应缓存可用时会参与后端缓存逻辑 |

### 3.2 后端依赖现状

`requirements.txt` 当前声明了：

- `fastapi>=0.100.0`
- `uvicorn>=0.30.0`
- `requests>=2.30.0`
- `apscheduler>=3.10.4`
- `pulp>=2.8.0`
- `lttbc>=0.3.0`
- `redis>=5.0.0`

根据代码实际使用情况，当前环境若要完整跑通后端测试，还需要关注 `pydantic`、`numpy`、`numpy-financial` 等依赖是否存在。

### 3.3 前端依赖准备

在 `web/` 目录执行：

```powershell
npm install
```

### 3.4 本地启动命令

后端：

```powershell
cd G:\project\aus-ele\backend
python -m uvicorn server:app --host 0.0.0.0 --port 8085
```

前端：

```powershell
cd G:\project\aus-ele\web
npm run dev
```

### 3.5 当前已知环境注意事项

- Python 自动化测试当前已可从仓库根目录直接执行，测试入口已补齐导入路径引导
- 后端自动化测试依赖当前 Python 环境中已安装 `fastapi`、`pulp` 等包
- 前端 `npm run build` 与 `lint` 当前均可通过，构建阶段的 CSS `@import` 告警已消除
- 部分抓取与同步验证依赖真实外部数据源，执行时应区分本地问题和上游数据源问题

## 4. 测试策略与执行方式

### 4.1 执行原则

- 以手工测试为主，当前自动化结果作为补充证据
- 先验证前后端启动与主链路，再验证分析模块，再验证同步与脚本
- 页面测试与接口测试并行开展，避免只看前端展示不看返回结构
- 对依赖外部数据源或历史回测的模块，优先验证“当前实现行为是否正确”，不把单次结果视为绝对业务真值

### 4.2 推荐执行顺序

1. 环境准备与服务启动
2. 首页加载、年份和区域筛选联动
3. 价格趋势、事件叠加、电网预测
4. 峰谷套利、FCAS、BESS 相关分析模块
5. 投资分析
6. 同步按钮与脚本验证
7. 自动化现状记录与回归收口

### 4.3 结果记录方式

- 每条用例执行后记录 `Pass`、`Fail` 或 `Blocked`
- 对 `Fail` 用例同步记录请求参数、接口响应、控制台日志或后端日志
- 对外部源导致的失败，需要单独标注为“上游依赖问题”或“本地环境问题”

## 5. 测试范围与非测试范围

### 5.1 测试范围

- 前端工作台
  - 首页加载与基础状态
  - 年份、区域、月份、季度、日类型筛选联动
  - 价格趋势
  - 事件叠加
  - 电网预测
  - 峰谷套利分析
  - FCAS 分析
  - BESS 模拟
  - 收入叠加
  - 充电窗口
  - 循环成本
  - 投资分析
  - 数据同步按钮与错误提示
- 后端 API
  - `/api/years`
  - `/api/summary`
  - `/api/price-trend`
  - `/api/event-overlays`
  - `/api/grid-forecast`
  - `/api/grid-forecast/coverage`
  - `/api/network-fees`
  - `/api/peak-analysis`
  - `/api/hourly-price-profile`
  - `/api/fcas-analysis`
  - `/api/investment-analysis`
  - `/api/sync_data`
- 数据脚本
  - NEM 抓取
  - WEM 抓取
  - WEM ESS slim 抓取
  - 事件同步脚本
  - 初始化/辅助脚本
- 自动化测试资产
  - Python `unittest`
  - 前端 `node:test`
  - 前端 `build/lint`

### 5.2 非测试范围

- 性能压测
- 安全渗透测试
- 完整浏览器兼容矩阵
- 移动端专项测试
- 生产环境灰度验证

## 6. 模块测试矩阵

| 模块 | 主要入口 | 主要测试类型 | 优先级 | 自动化覆盖现状 | 是否纳入发布回归 |
| --- | --- | --- | --- | --- | --- |
| 首页加载与筛选联动 | `web/src/App.jsx` | 手工功能、联动、错误状态 | P0 | 无直接 UI 自动化 | 是 |
| 价格趋势 | `/api/price-trend` + `PriceChart` | 接口、展示、空数据、筛选联动 | P0 | 后端部分间接覆盖 | 是 |
| 事件叠加 | `/api/event-overlays` + `eventOverlays.js` | 接口、事件覆盖、提示文案 | P1 | Python + Node 测试存在 | 是 |
| 电网预测 | `/api/grid-forecast` + `GridForecast.jsx` | 接口、覆盖模式、驱动展示 | P1 | Python + Node 测试存在 | 是 |
| 峰谷套利 | `/api/peak-analysis` + `PeakAnalysis.jsx` | 接口、聚合、网络费、图表 | P1 | 无稳定自动化门禁 | 是 |
| FCAS 分析 | `/api/fcas-analysis` + `FcasAnalysis.jsx` | NEM/WEM 双路径、容量参数、图表 | P1 | Python 部分覆盖 | 是 |
| BESS 模拟 | `BessSimulator.jsx` | UI、依赖数据加载、结果展示 | P2 | 无 | 否 |
| 收入叠加 | `RevenueStacking.jsx` | 组合展示、空数据、筛选联动 | P2 | 无 | 否 |
| 充电窗口 | `ChargingWindow.jsx` | 时段分布、图表、空数据 | P2 | 无 | 否 |
| 循环成本 | `CycleCost.jsx` | 数据加载、参数输入、结果展示 | P2 | 无 | 否 |
| 投资分析 | `/api/investment-analysis` + `InvestmentAnalysis.jsx` | 提交、结果结构、错误提示 | P0 | 前端 helper 有 Node 测试，后端自动化不稳定 | 是 |
| 元数据接口 | `/api/years`、`/api/summary`、`/api/network-fees` | 接口结构与可用性 | P1 | 无 | 是 |
| 数据同步 | `/api/sync_data` + `scrapers/*.py` | 手工触发、脚本执行、写库验证 | P0 | 无稳定自动化门禁 | 是 |

## 7. 详细测试用例

### 7.1 用例模板

每条测试用例统一包含以下字段：

- 用例编号
- 所属模块
- 优先级
- 测试类型
- 前置条件
- 测试步骤
- 输入/操作
- 预期结果
- 结果记录
- 备注/风险

### 7.2 前端总入口与筛选联动

#### TC-FE-SMOKE-001 首页默认加载

- 所属模块：前端总入口
- 优先级：P0
- 测试类型：手工功能测试
- 前置条件：前后端已启动；浏览器可访问前端页面
- 测试步骤：
  1. 打开前端首页
  2. 观察首屏是否出现年份、区域、导航与主要分析模块
  3. 等待默认数据加载完成
- 输入/操作：无
- 预期结果：
  - 页面可打开
  - 默认年份被选中
  - 默认区域为 `NSW1`
  - 页面未停留在永久 loading
  - 首页可看到价格趋势和后续分析模块入口
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：若后端未启动，前端可能进入错误态

#### TC-FE-FILTER-001 年份切换触发主数据刷新

- 所属模块：筛选联动
- 优先级：P0
- 测试类型：手工功能测试
- 前置条件：首页已加载完成
- 测试步骤：
  1. 记录当前年份
  2. 点击另一可用年份
  3. 观察价格趋势和统计卡片是否刷新
- 输入/操作：切换年份按钮
- 预期结果：
  - 年份高亮发生变化
  - 主图与统计区重新加载
  - 页面无未捕获错误
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：若数据库缺少对应年份数据，可能出现空结果

#### TC-FE-FILTER-002 月份与季度互斥

- 所属模块：筛选联动
- 优先级：P1
- 测试类型：手工功能测试
- 前置条件：首页已加载完成
- 测试步骤：
  1. 选择季度 `Q1`
  2. 展开月份过滤
  3. 再选择月份 `04`
  4. 观察季度是否被重置
- 输入/操作：季度与月份筛选切换
- 预期结果：
  - 选择月份后，季度不再保持之前的非 `ALL` 状态
  - 页面仍能正常刷新数据
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：该逻辑用于避免前端发送互相冲突的时间筛选

### 7.3 价格趋势

#### TC-FE-PRICE-001 价格趋势正常展示

- 所属模块：价格趋势
- 优先级：P0
- 测试类型：手工功能测试
- 前置条件：后端 `/api/price-trend` 返回非空数据
- 测试步骤：
  1. 进入首页默认视图
  2. 观察价格趋势图、统计卡片和小时分布图
- 输入/操作：无
- 预期结果：
  - 折线图正常渲染
  - 统计卡片显示最小值、最大值、平均值等指标
  - 小时分布图正常显示负价分布
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：若触发后端采样逻辑，返回点数可能小于总点数

#### TC-FE-PRICE-002 空数据场景

- 所属模块：价格趋势
- 优先级：P1
- 测试类型：手工功能测试
- 前置条件：选择一个当前无数据的时间窗口，或模拟后端返回空数组
- 测试步骤：
  1. 切换到空数据窗口
  2. 观察图表区域与统计区域
- 输入/操作：选择空数据筛选条件
- 预期结果：
  - 页面不崩溃
  - 图表区域显示空态或无记录提示
  - 统计区不出现明显错位或 JS 报错
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：空数据不应被误判为接口异常

### 7.4 事件叠加

#### TC-FE-EVENT-001 事件覆盖提示随筛选变化

- 所属模块：事件叠加
- 优先级：P1
- 测试类型：手工功能测试
- 前置条件：后端 `/api/event-overlays` 在当前区域至少存在一组事件状态
- 测试步骤：
  1. 选择存在事件的年份和区域
  2. 观察价格图上的事件阴影区或事件提示
  3. 切换月份和日类型
  4. 再次观察事件提示是否变化
- 输入/操作：切换时间筛选
- 预期结果：
  - 事件覆盖提示会跟随筛选刷新
  - 无事件时出现“无已验证事件解释”之类空态
  - 有事件时可看到覆盖级别或核心状态提示
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：该模块依赖事件同步结果和区域匹配逻辑

### 7.5 电网预测

#### TC-FE-FORECAST-001 24h 预测正常返回

- 所属模块：电网预测
- 优先级：P1
- 测试类型：手工功能测试
- 前置条件：后端 `/api/grid-forecast` 可用
- 测试步骤：
  1. 打开电网预测模块
  2. 保持区域为 `NSW1`
  3. 选择 `24h`
  4. 观察 summary cards、timeline、drivers
- 输入/操作：切换 horizon 到 `24h`
- 预期结果：
  - 模块成功加载
  - 出现风险或机会分数卡片
  - 出现未来窗口或驱动因子列表
  - 页面未出现未处理错误
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：NEM `24h` 预测会受外部 predispatch 数据可用性影响

#### TC-FE-FORECAST-002 覆盖模式提示正确

- 所属模块：电网预测
- 优先级：P1
- 测试类型：手工功能测试
- 前置条件：分别选择 `NSW1` 与 `WEM`
- 测试步骤：
  1. 观察 `NSW1` 的预测模块覆盖提示
  2. 切换区域到 `WEM`
  3. 再观察覆盖提示与 warning
- 输入/操作：切换区域
- 预期结果：
  - `NEM` 区域可出现 `full` 或 `partial` 类覆盖提示
  - `WEM` 区域显示 `core_only` 相关提示
  - 模块明确不是 investment-grade 预测
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：这是当前预测模块可信边界的重要验证点

### 7.6 峰谷套利分析

#### TC-FE-PEAK-001 峰谷套利结果可加载并切换聚合粒度

- 所属模块：峰谷套利
- 优先级：P1
- 测试类型：手工功能测试
- 前置条件：后端 `/api/peak-analysis` 可用
- 测试步骤：
  1. 打开峰谷套利模块
  2. 记录默认聚合粒度
  3. 依次切换 `daily`、`weekly`、`monthly`
- 输入/操作：切换聚合按钮
- 预期结果：
  - 数据随聚合粒度变化刷新
  - 图表与 summary 不报错
  - 网络费默认值或覆盖值显示正常
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：该接口依赖不同区域对应的窗口大小和网络费策略

### 7.7 FCAS 分析

#### TC-FE-FCAS-001 NEM FCAS 正常展示

- 所属模块：FCAS
- 优先级：P1
- 测试类型：手工功能测试
- 前置条件：所选 NEM 年份存在 FCAS 字段数据
- 测试步骤：
  1. 选择 NEM 区域
  2. 打开 FCAS 分析模块
  3. 调整容量参数
- 输入/操作：更改容量 MW 数值
- 预期结果：
  - breakdown、hourly、time series 可正常展示
  - 容量变化会影响估算收入
  - 页面不报错
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：若年份表中 FCAS 列为空，模块应返回无数据提示而非崩溃

#### TC-FE-FCAS-002 WEM FCAS 显示预览性质

- 所属模块：FCAS
- 优先级：P1
- 测试类型：手工功能测试
- 前置条件：WEM ESS slim 表存在数据
- 测试步骤：
  1. 切换区域为 `WEM`
  2. 打开 FCAS 模块
  3. 观察 summary 区和说明文案
- 输入/操作：无
- 预期结果：
  - 模块可展示 WEM 预览结果
  - summary 中明确显示预览模式或非 investment-grade 属性
  - 若仅单日覆盖，能看到 `single_day_preview` 语义
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：WEM 当前为 slim 数据，不应误判为完整投资级结论

### 7.8 投资分析

#### TC-FE-INVEST-001 投资分析可提交并返回结果

- 所属模块：投资分析
- 优先级：P0
- 测试类型：手工功能测试
- 前置条件：后端 `/api/investment-analysis` 可用
- 测试步骤：
  1. 滚动到投资分析模块
  2. 修改一个参数，例如 `discount_rate`
  3. 点击“运行分析”
  4. 观察结果区
- 输入/操作：修改参数并提交
- 预期结果：
  - 请求成功发出
  - 返回 `base_metrics`、`scenarios`、`monte_carlo` 等结果结构
  - 页面显示 NPV、IRR、Payback 等结果
  - 失败时展示错误提示，而不是静默无响应
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：当前后端投资分析的自动化回归并不稳定，人工验证是发布前重点

#### TC-FE-SYNC-001 数据同步按钮可触发后台任务

- 所属模块：同步按钮
- 优先级：P0
- 测试类型：手工功能测试
- 前置条件：后端服务已启动
- 测试步骤：
  1. 点击页面右上角同步按钮
  2. 观察按钮 loading 状态与弹窗提示
  3. 检查后端日志是否收到同步触发
- 输入/操作：点击同步按钮
- 预期结果：
  - 按钮进入短暂同步状态
  - 页面出现“数据同步已在后台启动”提示
  - 后端收到 `/api/sync_data` 请求
  - 接口返回 `{ "status": "Update started in background" }`
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：该操作会触发真实抓取脚本，应区分接口触发成功与抓取最终成功

### 7.9 核心 API

#### TC-API-CORE-001 `/api/years` 返回年份列表

- 所属模块：元数据接口
- 优先级：P1
- 测试类型：接口测试
- 前置条件：后端服务已启动；数据库存在 `trading_price_*` 表
- 测试步骤：
  1. 发送 `GET /api/years`
  2. 检查响应结构
- 输入/操作：无
- 预期结果：
  - HTTP 状态为 `200`
  - 返回体包含 `years`
  - `years` 为按年倒序排列的数组
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：若数据库为空，返回列表可能为空

#### TC-API-CORE-002 `/api/summary` 返回表摘要和更新时间

- 所属模块：元数据接口
- 优先级：P1
- 测试类型：接口测试
- 前置条件：数据库已有基础数据
- 测试步骤：
  1. 发送 `GET /api/summary`
  2. 检查 `tables` 和 `last_update`
- 输入/操作：无
- 预期结果：
  - HTTP 状态为 `200`
  - 返回体包含 `tables`
  - 若有更新记录，则包含 `last_update`
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：该接口用于首页初始化

#### TC-API-PRICE-001 `/api/price-trend` 非法年份处理

- 所属模块：价格趋势接口
- 优先级：P1
- 测试类型：接口异常测试
- 前置条件：后端服务已启动
- 测试步骤：
  1. 发送一个不存在年份的请求，如 `GET /api/price-trend?year=1999&region=NSW1`
  2. 观察响应
- 输入/操作：非法年份
- 预期结果：
  - 返回 `404` 或明确的无数据错误
  - 服务不崩溃
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：错误语义应与当前实现保持一致

#### TC-API-EVENT-001 `/api/event-overlays` 时间过滤正确

- 所属模块：事件叠加接口
- 优先级：P1
- 测试类型：接口测试
- 前置条件：数据库存在多月份事件数据
- 测试步骤：
  1. 发送 `GET /api/event-overlays?year=2026&region=NSW1&month=04&day_type=WEEKDAY`
  2. 检查 `states`、`daily_rollup`、`metadata.filters`
- 输入/操作：月份和日类型筛选
- 预期结果：
  - 返回体中的事件状态与日期滚动结果符合筛选条件
  - `metadata.coverage_quality` 存在
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：当前覆盖级别还依赖事件同步状态表

#### TC-API-FORECAST-001 `/api/grid-forecast/coverage` 返回覆盖摘要

- 所属模块：预测接口
- 优先级：P1
- 测试类型：接口测试
- 前置条件：后端服务已启动
- 测试步骤：
  1. 发送 `GET /api/grid-forecast/coverage?market=NEM&region=NSW1&horizon=24h`
  2. 检查 `coverage_quality`、`sources_used`、`source_status`
- 输入/操作：标准 NEM 请求
- 预期结果：
  - HTTP 状态为 `200`
  - 返回覆盖质量、来源列表、来源状态
  - 结果结构与前端展示需求一致
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：不同市场和时域的覆盖质量可能不同

#### TC-API-FCAS-001 `/api/fcas-analysis` WEM 返回预览语义

- 所属模块：FCAS 接口
- 优先级：P1
- 测试类型：接口测试
- 前置条件：WEM ESS slim 表存在数据
- 测试步骤：
  1. 发送 `GET /api/fcas-analysis?year=2026&region=WEM&aggregation=daily&capacity_mw=100`
  2. 检查 `summary`
- 输入/操作：WEM 请求
- 预期结果：
  - 返回 `has_fcas_data`
  - 返回 summary 中的 `preview_mode`、`coverage_days` 或预览性质说明
  - 不把结果标记为 investment-grade
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：当前 WEM 结果基于 slim 表估算

#### TC-API-INVEST-001 `/api/investment-analysis` 返回关键结果结构

- 所属模块：投资分析接口
- 优先级：P0
- 测试类型：接口测试
- 前置条件：后端服务已启动
- 测试步骤：
  1. 向 `/api/investment-analysis` 发送最小合法 JSON
  2. 检查响应结构
- 输入/操作：合法 POST 请求体
- 预期结果：
  - 返回 `region`
  - 返回 `base_metrics`
  - 返回 `scenarios`
  - 若启用蒙特卡洛，则返回 `monte_carlo`
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：当前接口与部分旧测试预期存在漂移，需以当前实现结构为准

### 7.10 数据同步与脚本

#### TC-SCRIPT-SYNC-001 事件同步脚本可启动

- 所属模块：事件同步脚本
- 优先级：P0
- 测试类型：脚本执行测试
- 前置条件：Python 环境可用
- 测试步骤：
  1. 执行 `python scrapers/aemo_grid_event_scraper.py --days 180`
  2. 观察日志输出
  3. 检查数据库事件相关表是否更新
- 输入/操作：`--days 180`
- 预期结果：
  - 脚本可启动
  - 日志中出现同步结果
  - 数据库中的事件原始表或状态表有更新迹象
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：真实执行依赖外部官方源可访问

#### TC-SCRIPT-WEMESS-001 WEM ESS slim 脚本可启动

- 所属模块：WEM ESS slim 脚本
- 优先级：P0
- 测试类型：脚本执行测试
- 前置条件：Python 环境可用
- 测试步骤：
  1. 执行 `python scrapers/aemo_wem_ess_scraper.py --days 30`
  2. 观察日志输出
  3. 检查 `wem_ess_market_price`、`wem_ess_constraint_summary` 是否有数据变化
- 输入/操作：`--days 30`
- 预期结果：
  - 脚本可启动
  - 日志显示覆盖范围和写入统计
  - slim 表存在可验证更新
- 结果记录：执行时填写 Pass / Fail / Blocked
- 备注/风险：下载失败时需区分网络问题与源站问题

## 8. 自动化测试现状

### 8.1 后端自动化

当前后端自动化主要位于：

- `tests/test_event_overlays.py`
- `tests/test_grid_forecast.py`
- `tests/test_non_engineering_fixes.py`
- `tests/test_wem_ess_slim.py`
- `backend/test_investment_api.py`

当前执行现状：

| 检查项 | 命令 | 当前结果 | 说明 |
| --- | --- | --- | --- |
| 默认 `unittest` 发现 | `python -m unittest discover -s tests -v` | 失败 | 主要因为 `database`、`bess_backtest` 等模块无法从仓库根目录直接导入 |
| 设置 `PYTHONPATH` 后重试 | `$env:PYTHONPATH='G:\project\aus-ele\backend'; python -m unittest discover -s tests -v` | 失败 | 当前环境缺少 `fastapi`、`pulp` 等依赖 |
| 单独投资分析测试 | `$env:PYTHONPATH='G:\project\aus-ele\backend'; python -m unittest backend.test_investment_api -v` | 未形成稳定入口 | 当前环境与模块导入方式仍不稳定 |

### 8.2 前端自动化

当前前端自动化主要位于：

- `web/src/lib/apiClient.test.js`
- `web/src/lib/gridForecast.test.js`
- `web/src/lib/eventOverlays.test.js`
- `web/src/lib/investmentAnalysis.test.js`
- `web/src/lib/eventPanelPlacement.test.js`

当前执行现状：

| 检查项 | 命令 | 当前结果 | 说明 |
| --- | --- | --- | --- |
| Node 原生测试 | `node --test src\lib\apiClient.test.js src\lib\gridForecast.test.js src\lib\eventOverlays.test.js src\lib\investmentAnalysis.test.js src\lib\eventPanelPlacement.test.js` | 通过 | 当前已验证 `17/17` 通过 |
| `package.json` 标准 `test` 脚本 | 无 | 缺失 | 当前测试未接入统一脚本入口 |

### 8.3 工程校验

| 检查项 | 命令 | 当前结果 | 说明 |
| --- | --- | --- | --- |
| 前端构建 | `.\node_modules\.bin\vite.cmd build` | 通过 | 已拆分重分析面板，当前构建无 CSS `@import` 与大包体积警告 |
| 前端 lint | `.\node_modules\.bin\eslint.cmd .` | 通过 | 当前 ESLint 基线已拉平 |

## 9. 已知测试缺口与质量风险

- Python 自动化测试默认入口不稳定，存在导入路径依赖
- 后端自动化测试受当前本机 Python 环境依赖是否齐全影响较大
- 前端静态检查当前可通过，但懒加载后的占位态与弱网加载体验仍需继续关注
- 多个分析模块依赖真实历史数据与外部同步结果，部分验证只能做到“当前实现行为正确”，不能直接证明业务结论绝对正确
- 数据同步与预测相关能力受外部官方源可用性影响

## 10. 回归测试清单

发布前至少完成以下回归：

- 前后端服务均可启动
- 首页默认加载成功
- 年份与区域筛选联动正常
- `/api/years`、`/api/summary`、`/api/price-trend` 可用
- 价格趋势图可展示
- 事件叠加接口和页面提示正常
- 电网预测模块可返回结果
- 峰谷套利与 FCAS 模块可加载
- 投资分析可提交并返回结果
- 同步按钮可触发后台任务
- 前端 `vite build` 可通过
- 前端 Node 测试可通过

## 11. 缺陷等级与提交流程

### 11.1 缺陷等级

| 等级 | 定义 | 例子 |
| --- | --- | --- |
| P0 | 阻断系统主链路或阻断发布 | 服务启动失败、首页不可用、投资分析无法提交 |
| P1 | 核心模块错误或结果明显异常 | 价格趋势错误、预测模块无响应、FCAS 结果结构错误 |
| P2 | 次要问题或体验问题 | 文案错误、样式问题、边界状态提示不清 |

### 11.2 缺陷记录最少字段

- 缺陷标题
- 发现版本或分支
- 发现时间
- 所属模块
- 环境信息
- 复现步骤
- 实际结果
- 预期结果
- 严重级别
- 附件（日志、截图、响应体）

## 12. 发布前验收标准

满足以下条件时，可认为当前版本通过基础 QA 验收：

- P0 缺陷为 `0`
- 核心 P1 缺陷已处理完毕，或已明确评估不阻断发布
- 回归清单中的必测项执行完成
- 前端构建通过
- 前端 Node 自动化通过
- 关键 API 可正常返回

以下情况默认阻断发布：

- 首页无法加载
- 任一核心 API 持续 500
- 电网预测、价格趋势、投资分析主链路不可用
- 同步入口触发即失败且无替代操作路径
