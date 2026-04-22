# AEMO Intelligence - Australian NEM/WEM Data Explorer (aus-ele)

**AEMO 澳洲电网智能观测站** 

这是一个针对澳大利亚国家电力市场（NEM）与西澳电力市场（WEM）的高保真、极致极简主义数据观测工作台。该系统旨在通过自动化爬取、海量数据聚合分析以及现代化的前端可视化技术，帮助交易员、研究人员和能源分析师观测并研究澳洲电网历史以来的高频价格波动、反向溢价（负电价）、异常结算报价特征以及储能电池（BESS）套利模型。

---

## 🌟 核心功能模块详细说明 (Detailed Features)

系统分为底层数据采集、强力运算层与可视化工作台三个部分，提供了极具深度的功能：

### 1. 深度异常量化与风控统计 (Anomalous Bidding & Risk Analytics)
系统在聚合了基础的 **峰值 (Peak)**、**谷值 (Floor)** 与 **均值结算 (Mean Settlement)** 后，引入了一块被称为 `DEEP DIVE` 的极值定制化分析引擎，提供用于风控和衍生品交易所需的关键数据：
* **负电价发生概率 (Negative Frequency)**：计算发生低于 $0/MWh 的结算区间占比。
* **极端负向穿透天数 (Extreme Floor Exceedance)**：计算电价深度跌破 A$-100 的独立发生天数。
* **缺电溢价/Cap合约触碰天数 (Days > A$300)**：专门计算现货飙升超过 300 澳元/兆瓦时的高保真风险天数。

### 2. 多市场与全频率辅助服务支持 (NEM & WEM, 10-Class FCAS)
* **WEM 市场深度集成**：完整支持西澳（WEM）历史电价、ESS（能量与辅助服务）海量数据，并通过动态年份分表（Slim Tables）解决百万级数据并发检索的性能瓶颈。
* **10 类 FCAS 全解析**：系统已实装 NEM 最新规范的 10 类 FCAS 数据字段解析，包括全新的 `raise1sec_rrp` 和 `lower1sec_rrp`（Very Fast FCAS 1秒级辅助服务市场），数据维度已达顶尖工业级规格。

### 3. 图表视觉降采样算法 (LTTB Algorithm)
由于 AEMO 5 分钟结算导致单区域全年结算点位高达 10.5 万个，直接输送给前端会导致浏览器内存溢出崩溃：
* 后端废弃了简易的极大极小值包络，**全量实装了真正的 LTTB (Largest-Triangle-Three-Buckets) 算法**（利用 Numpy 与 C 扩展 `lttbc`），实现完美的数学级视觉降采样。
* 在折叠上万条数据的同时，完美保留每一个物理尖峰与负价格谷底，保证 UI 上的折线图毛刺（极值）绝不会被平滑掉。

### 4. 电池储能 (BESS) 回测与滑动窗口分析 (BESS Backtesting & Analytics)
* 内置大储（Utility-Scale Battery）套利模型计算逻辑，支持基于真实电价的充放电收益估算。
* 提供针对全天序列的 Running Sum 滑动窗口扫描，自动对接各州网络使用费（TUOS/DUOS）计算纯净利润价差（Net Spread）。

---

## 🏗️ 架构概览与目录规范 (Architecture & Tech Stack)

系统已完成高度模块化的工程重构，目录职责隔离清晰：

*   📁 **`backend/` (核心服务层)**：基于 `FastAPI` 构建 API 网关（`server.py`），提供所有数据查询路由，并内嵌 `AsyncIOScheduler` 用于每晚自动触发后台爬虫子进程。底层通过 SQLite 动态分表驱动（`database.py`）并融合了基于 Redis 的高速响应缓存机制（`response_cache.py`）。
*   📁 **`scrapers/` (数据采集层)**：专门存放与 AEMO 交互的网络爬虫脚本（如 `aemo_nem_scraper.py`、`aemo_wem_scraper.py` 等），支持自动化解析 CSV 压缩包、断点续传与幂等更新。
*   📁 **`data/` (持久化层)**：存放底层的 `.db` SQLite 物理文件，全局开启 WAL 模式 (Write-Ahead Logging) 解决并发读写锁定问题。
*   📁 **`scripts/` (运维脚本层)**：存放全量历史数据初始化工具（如 `init_wem_history.py`）与数据库健康巡检工具。
*   📁 **`docs/` (文档库)**：存放所有架构分析、审计报告、算法业务逻辑说明（包含重构分析报告）。
*   📁 **`web/` (前端工作台)**：React + Vite + Tailwind CSS + Framer Motion 构建的轻量化极简暗黑主题 SPA 监控面板。

---

## 🚀 本地启动指引 (Quick Start)

**1. 后端依赖安装与启动**
```bash
pip install fastapi uvicorn requests bs4 lttbc redis apscheduler pandas numpy
cd backend
python -m uvicorn server:app --host 0.0.0.0 --port 8085
# 启动将会监听 localhost:8085，同时自动挂载每晚的背景爬虫同步定时任务。
```

**2. 前端启动**
```bash
cd web
npm install
npm run dev
# 访问 http://localhost:5173 打开智能观测站。
```

*(备注：若本地无数据，请先执行 `scripts/` 目录下的相关工具初始化 `data/aemo_data.db` 实体数据库。)*

---

*This repository is built for quantitative analysis and visualization of absolute grid fluctuations. Discover anomalous bidding behaviors inside the Australian Electrical System.*