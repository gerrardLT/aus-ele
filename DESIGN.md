# AEMO BESS 投资仪表板 — 设计系统

> 本文档是项目的设计系统源文件（Single Source of Truth），所有前端决策应参照此文件。

---

## 1. 产品定位

| 维度 | 定义 |
|------|------|
| **产品名称** | AEMO Intelligence — 澳洲电网智能观测站 |
| **用户画像** | 储能投资分析师、电力交易员、能源基金 PM，具备 NEM 市场基础知识 |
| **使用场景** | 桌面端（≥1280px），数据密集型分析工作台，单次使用 30-90 分钟 |
| **核心任务** | 评估 BESS 储能投资回报：价差套利 → FCAS 叠加 → 现金流测算 |
| **品牌调性** | 工业极简 / 瑞士制表精度 / 彭博终端克制感 |

---

## 2. 设计原则

### 2.1 核心原则

1. **数据优先 (Data-First)**
   - 数据是主角，装饰性元素是配角
   - 每个视觉元素必须传递信息，否则删除
   - 信息密度：专业用户期待高密度，但需要清晰的层级

2. **安静权威 (Quiet Authority)**
   - 不使用渐变色、发光效果或过度动画
   - 通过排版层级和留白建立专业感
   - 色彩克制：语义色用于传达含义，而非装饰

3. **渐进式披露 (Progressive Disclosure)**
   - 默认展示最关键的信息
   - 高级选项通过折叠面板按需展开
   - 工具提示解释专业术语

4. **可预测性 (Predictability)**
   - 相同类型的交互使用相同的视觉模式
   - 过滤器、按钮、卡片的样式全局一致
   - 用户无需学习新的交互范式

---

## 3. 色彩系统

### 3.1 CSS 变量定义

```css
:root {
  /* 基础 */
  --color-bg:             #FFFFFF;        /* 页面背景 */
  --color-surface:        #F9FAFB;        /* 卡片/面板背景 */
  --color-surface-hover:  #F3F4F6;        /* 面板悬停 */
  --color-text:           #050505;        /* 正文文字 */
  --color-muted:          #8E8E8E;        /* 次级文字/标签 */
  --color-border:         #E5E5E5;        /* 分割线/边框 */

  /* 反转 (按钮/导航激活态) */
  --color-inverted:       #050505;        /* 深色背景 */
  --color-inverted-text:  #FFFFFF;        /* 深色背景上的文字 */

  /* 语义色 */
  --color-primary:        #0047FF;        /* 品牌蓝 — 唯一的强调色 */
  --color-error:          #E53E3E;        /* 错误/亏损/负值 */
  --color-positive:       #22C55E;        /* 盈利/正向指标 */
  --color-warning:        #F59E0B;        /* 警告/边界值 */
}
```

### 3.2 色彩使用规则

| 颜色 | 用途 | 禁止 |
|------|------|------|
| `#0047FF` 品牌蓝 | 主 CTA 按钮、关键链接、品牌标识 | 不用于数据可视化中的负值 |
| `#22C55E` 正向绿 | NPV > 0、IRR 达标、盈利区间 | 不用于装饰 |
| `#EF4444` 风险红 | NPV < 0、亏损、错误状态 | 不用于 CTA 按钮 |
| `#F59E0B` 警告橙 | IRR 低于贴现率、边界利润区间 | 不与绿色混用于同一指标 |
| `#050505` 纯黑 | 激活态按钮、表头、最高级标题 | 不用于正文段落（太重） |
| `#8E8E8E` 灰 | 标签、副标题、非活动状态 | 不用于主标题 |

### 3.3 图表配色方案

```javascript
const CHART_PALETTE = {
  arbitrage:  '#0047FF',  // 套利收入
  fcas:       '#22C55E',  // FCAS 收入
  loss:       '#EF4444',  // 损耗/扣减
  marginal:   '#F59E0B',  // 边界值
  baseline:   '#E5E5E5',  // 参考线
  area_fill:  'rgba(0, 71, 255, 0.08)', // 面积图填充
};
```

---

## 4. 排版系统

### 4.1 字体栈

```css
--font-sans:  'Inter', ui-sans-serif, system-ui, sans-serif;
--font-serif: 'Playfair Display', ui-serif, Georgia, serif;
```

| 用途 | 字体 | 权重 | 间距 |
|------|------|------|------|
| **页面标题 (h1)** | Playfair Display | 600 (Semi-Bold) | -0.02em |
| **章节标题 (h2)** | Playfair Display | 400 (Regular) | -0.02em |
| **模块标题 (h3-h4)** | Inter | 700 (Bold) | 0.05em, UPPERCASE |
| **正文/数据** | Inter | 400 | 0 |
| **标签/辅助文字** | Inter | 500-600 | 0.08em, UPPERCASE |
| **数据数值** | Inter (font-mono) | 700 | 0 |

### 4.2 字号规模

```
text-xs:   12px  — 标签、辅助信息、tracking-wider
text-sm:   14px  — 过滤器按钮、表格内容
text-base: 16px  — 段落正文
text-lg:   18px  — 导航品牌名
text-xl:   20px  — 模块副标题
text-2xl:  24px  — KPI 数值
text-3xl:  30px  — 章节标题 (h2)
```

---

## 5. 空间与布局

### 5.1 网格系统

```css
.grid-container {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 24px;
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 32px;
}
```

### 5.2 间距规则

| 层级 | 间距 | 用途 |
|------|------|------|
| **模块间** | `mt-16 pt-12` (约 112px) | 顶层 section 之间 |
| **组件间** | `gap-12` (48px) | 同一 section 内的图表/表卡之间 |
| **元素间** | `gap-4` (16px) | 表格行、过滤器按钮之间 |
| **内边距** | `p-4` (16px) | 卡片/面板内部 |

### 5.3 断点

| 断点 | 宽度 | 布局 |
|------|------|------|
| Mobile | < 768px | 单列，12/12 |
| Tablet | 768-1024px | 简化双列 |
| Desktop | > 1024px | 完整 12 列网格（3+9 或 4+8） |

---

## 6. 组件规范

### 6.1 过滤器按钮

```
活动态:   bg-inverted text-inverted-text rounded-full border-inverted
非活动态: bg-transparent text-text border-border rounded-full
悬停态:   border-text
尺寸:     min-h-[44px] px-5 py-2 text-sm
```

### 6.2 KPI 卡片

```
容器:     border border-border p-4 rounded-lg
标签:     text-xs text-muted UPPERCASE tracking-wider
数值:     text-2xl font-bold font-mono (颜色语义化)
副信息:   text-xs text-muted mt-1
```

### 6.3 Section 标题

```
标题:     text-3xl font-serif (h2)
对齐标签: text-muted text-sm tracking-widest UPPERCASE font-bold (右对齐)
分隔线:   border-t border-border
```

### 6.4 加载状态
```
容器:     h-64 flex items-center justify-center
文字:     font-serif text-lg text-muted
内容:     (描述正在做什么)... 大约需要 X 秒
```

### 6.5 错误状态
```
容器:     p-4 border border-red-300 bg-red-50 text-red-700 rounded
内容:     (说明什么出错了) + (建议下一步操作)
```

---

## 7. 交互模式

### 7.1 动效

| 场景 | 动画 | 时长 |
|------|------|------|
| 页面加载 | opacity 0→1, y 10→0 | 600ms ease-out |
| 面板展开 | height 0→auto, opacity 0→1 | 200ms |
| 按钮悬停 | scale 1→1.1 | transition-transform |
| 数据切换 | opacity 0→1, x 20→0 | 500ms ease-out |

### 7.2 渐进式披露

- 月份过滤器默认折叠
- TOC 导航面板点击展开
- InvestmentAnalysis 参数分组折叠
- Tooltip 解释专业术语

### 7.3 无障碍

- 所有交互元素 `min-h-[44px]` (WCAG touch target)
- `aria-label` 用于图标按钮
- 颜色不作为唯一信息载体（配合文字/图标）
- Tooltip 支持键盘 focus

---

## 8. UX 写作规范

### 8.1 双语策略

- **中文为主语言** — 所有界面默认中文
- **英文为辅助** — 关键标签后括号标注英文术语
- **格式**: `中文名 / ENGLISH_KEY` 或 `中文 (ABBR)`
- **示例**: `储能套利分析`, `过网费 ($/MWh)`, `运行分析 / RUN ANALYSIS`

### 8.2 术语一致性

| 术语 | 中文 | 英文 | 用法 |
|------|------|------|------|
| NPV | 净现值 | Net Present Value | 投资分析 KPI |
| IRR | 内部收益率 | Internal Rate of Return | 投资分析 KPI |
| FCAS | 调频辅助服务 | Frequency Control Ancillary Services | 收入来源 |
| RTE | 循环效率 | Round-Trip Efficiency | 储能参数 |
| MLF | 边际网损系数 | Marginal Loss Factor | 输电损耗 |
| CAPEX | 资本支出 | Capital Expenditure | 投资成本 |
| Spread | 价差 | Price Spread | 套利区间 |
| 过网费 | 过网费 | Network Fee | TUoS + DUoS |

### 8.3 错误消息规范

```
❌ 错误: "Error" / "Failed" / 技术性错误码
✅ 正确: 说明什么出了问题 + 建议操作

示例:
  "无法加载 FCAS 数据。请检查后端服务是否运行，或稍后重试。"
  "投资分析计算失败：回测年份数据不足。请选择有完整数据的年份。"
```

### 8.4 加载消息规范

```
❌ 错误: "Loading..." (无上下文)
✅ 正确: 说明正在做什么

示例:
  "正在计算套利窗口..." (PeakAnalysis)
  "正在加载 FCAS 调频数据..." (FcasAnalysis)
  "正在模拟全要素利润..." (BessSimulator)
```

---

## 9. 反模式清单 (AI Slop)

以下模式在本项目中**严格禁止**：

| 反模式 | 替代方案 |
|--------|---------|
| 渐变文字 | 纯色文字 + 语义色 |
| 发光边框/光晕效果 | 1px 实线边框 |
| 弹性/回弹动画 | ease-out 减速 |
| 深色模式 + 霓虹色 | 纯白背景 + 黑色/蓝色 |
| 玻璃拟态 (blur) | 实色背景 |
| 装饰性图标 (大圆角矩形+图标) | 文字 + 数字 |
| 卡片嵌套卡片 | 扁平层级 |
| "Hero metric" 模板 | 内联 KPI 卡片组 |

---

## 10. 版本记录

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-04-09 | 初始设计系统文档化 |
