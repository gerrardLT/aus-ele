# AEMO Intelligence - Australian NEM Data Explorer (aus-ele)

**AEMO 澳洲电网智能观测站** 

这是一个针对澳大利亚国家电力市场（National Electricity Market, NEM）的高保真、极致极简主义数据观测工作台。该系统旨在通过自动化爬取、海量数据聚合分析以及现代化的前端可视化技术，帮助交易员、研究人员和能源分析师观测并研究澳洲电网历史以来的高频价格波动、反向溢价（负电价）以及异常结算报价特征。

---

## 🌟 核心功能模块详细说明 (Detailed Features)

系统分为底层数据采集、强力运算层与可视化工作台三个部分，提供了极具深度的功能：

### 1. 多维度时空切片查询 (Multi-Dimensional Temporal & Geospatial Engine)
除了提供基于**五大物理选区**（NSW 新州、QLD 昆州、VIC 维州、SA 南澳、TAS 塔州）的维度下钻外，本观测站提供极其精细的时间周期过滤：
* **年度与多重季节过滤**：支持指定具体月份，或按澳洲特有的电力供需季节规律过滤（如 `Q1 (夏季极值)`、`Q3 (冬季极值)` 等）。
* **负荷曲线结构分离**：支持一键剥离 `工作日 (Weekday)` 与 `周末 (Weekend)` 的结算数据。由于工业负荷与居民负荷在工作日和周末形成鲜明跨度，这一功能可以快速暴露出周末白天的严重负电价塌陷现象。

### 2. 深度异常量化与风控统计 (Anomalous Bidding & Risk Analytics)
系统在聚合了基础的 **峰值 (Peak)**、**谷值 (Floor)** 与 **均值结算 (Mean Settlement)** 后，引入了一块被称为 `DEEP DIVE` 的极值定制化分析引擎，提供用于风控和衍生品交易所需的六大关键数据：
* **负电价发生概率 (Negative Frequency)**：计算指定时间/截面内发生低于 $0/MWh 的结算区间所占的百分率。在光伏大发的南澳等地，此数值往往极高。
* **负电价均界 (Negative Mean)**：精准剥离正电价干扰，仅对所有负溢价事件进行求均，评估极端出清的深度。
* **极端负向穿透天数 (Extreme Floor Exceedance)**：计算电价深度跌破 A$-100 的独立发生天数。
* **缺电溢价/Cap合约触碰天数 (Days > A$300)**：专门计算现货飙升超过 300 澳元/兆瓦时（触发传统 Cap 封顶合约赔付警戒线）的极端天数。
* **剥离零值后的常规均界 (Positive Mean)**：严格在电价 `> $0` 的前提下计算均值，防止被频繁的 `$0` 弃风/弃光时段污染。

### 3. 海量现货数据的安全采样与高保真图表 (High-Frequency Envelope Point Sampling)
由于 AEMO 在 2021 年底普及了 5 分钟结算，单一区域全年的结算点位高达令人发指的 10.5 万个。直接输送给前端会导致浏览器内存溢出崩溃：
* 后端使用了高度优化的 **峰顶保留包络降采样算法 (Peak-Preserving Envelope Sampling)**。
* 在折叠上万条数据的同时，完美保留每一个物理尖峰与负价格谷底，保证 UI 上的折线图毛刺（极值）与数据库完全一一对应，绝不会因为数据抽样而削平了真正的极端风险点位。

### 4. 负电价 24 小时热力分布规律 (24-Hour Anomalous Time Distribution)
* 系统内置了一条以小时（按 24h 桶截断，并完美桥接了 AEMO 00:00 的期末结算时间戳漂移）为周期的分布柱状图。
* 明确展示一天中哪些小时最容易发生负电价事件（例如典型的“鸭子曲线”现象：正午由于分布式太阳能激增导致的大规模负区间）。

### 5. 高端无边框极简暗黑界面体系 (Imperial Slate / Minimalist UI)
* 前端采用了无边框、极大留白的极简设计逻辑（B2B 级 Imperial Slate 主题体系）。
* UI 无缝支持 **中 / ENG** 即时语言热切换验证展示，完美兼顾国内外业务汇报场景并具备零延迟的重度过滤更新体验。

---

## 🏗️ 架构概览 (Architecture & Tech Stack)

1. **自动化归档引擎 (Data Ingestion)**: 
   - `aemo_nem_scraper.py`
   - 利用 `BeautifulSoup` 和 `requests` 直连 AEMO 公开的 NEMWEB CSV 压缩包归档（`DATAARCHIVE/TradingIS_Reports`），支持百万级行记录自动解压爬取与清洗入库。
2. **高速边缘数据库 (Persistence)**:
   - `database.py` (SQLite3 with WAL mode)
   - 启用 `PRAGMA synchronous=NORMAL` 协程安全读写，通过表级别按季度/年份分区，保证快速扫描提取。
3. **计算后端 (Backend API)**:
   - `server.py` (FastAPI + Uvicorn)
   - 支持跨域调用的数据伺服层，融合了单次极速全表 Scan 定制化统计查询，响应速度极快。
4. **前端工作台 (Frontend View)**:
   - `web/` (React + Vite + Tailwind CSS + Framer Motion)
   - 轻量化的 SPA，使用 Recharts 驱动图表，辅以 Lucide-React 图标库。

---

## 🚀 本地启动指引 (Quick Start)

**1. 后端依赖安装与启动**
```bash
pip install fastapi uvicorn requests bs4
python server.py
# 启动将会监听 localhost:8085，同时挂载挂载 /api/price-trend 等计算路由。
```

**2. 前端启动**
```bash
cd web
npm install
npm run dev
# 访问 http://localhost:5173 打开智能观测站。
```

*(备注：需要事先运行脚本来归档生成 `aemo_data.db` 实体数据库。)*

---

*This repository is built for quantitative analysis and visualization of absolute grid fluctuations. Discover anomalous bidding behaviors inside the Australian Electrical System.*