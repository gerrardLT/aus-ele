# Requirements Document

## Introduction

AEMO Intelligence 平台当前将 WEM（西澳电力市场）作为 NEM（国家电力市场）的一个区域处理。实际上，WEM 和 NEM 是完全独立的市场，在"澳洲电力市场"层级下属于同级关系。两者在结算间隔、辅助服务类型、市场设计和时区方面存在根本差异。本功能将 WEM 分离为独立页面和路由，提供 WEM 专属的 UI 组件和分析能力，同时保持与 NEM 页面的共享组件复用。

## Glossary

- **Platform**: AEMO Intelligence 前端应用，基于 React 19 + Vite 8 构建的单页应用
- **Page_Router**: 前端路由解析模块（pageRouter.js），根据 URL 路径决定加载哪个页面组件
- **NEM_Page**: 国家电力市场分析页面，展示 NSW1、QLD1、VIC1、SA1、TAS1 五个区域的数据
- **WEM_Page**: 西澳电力市场专属分析页面，展示 WEM 市场数据和 ESS 分析
- **Region_Selector**: 区域选择器组件，允许用户在不同市场区域间切换
- **ESS**: Essential System Services，WEM 的辅助服务体系，包含 Regulation Raise/Lower、Contingency Raise/Lower、RoCoF 五种类型
- **FCAS**: Frequency Control Ancillary Services，NEM 的调频辅助服务体系，包含 8-10 种类型
- **Sidebar_Navigation**: 侧边栏导航组件，展示所有可用市场页面的入口
- **Shared_Components**: 可在多个市场页面复用的通用分析组件（如 InvestmentAnalysis、DataQualityBadge）
- **Settlement_Interval**: 结算间隔，NEM 为 5 分钟，WEM RTP 为 30 分钟
- **RTP**: Real-Time Price，WEM 实时价格，30 分钟结算间隔
- **ESS_Dispatch**: WEM ESS 调度间隔，5 分钟

## Requirements

### Requirement 1: WEM 独立路由

**User Story:** 作为平台用户，我希望通过独立的 URL 路径访问 WEM 市场页面，以便直接导航到西澳市场分析而无需经过 NEM 页面。

#### Acceptance Criteria

1. WHEN 用户访问 `/wem` 路径, THE Page_Router SHALL 解析该路径并返回 `wem` 页面标识
2. WHEN Page_Router 返回 `wem` 页面标识, THE Platform SHALL 加载 WEM_Page 组件
3. WHEN 用户访问 `/wem` 路径, THE Platform SHALL 使用 React lazy loading 按需加载 WEM_Page 组件
4. WHEN WEM_Page 组件加载中, THE Platform SHALL 展示与其他页面一致的加载占位状态

### Requirement 2: NEM 页面区域分离

**User Story:** 作为 NEM 市场分析师，我希望 NEM 页面仅展示 NEM 区域，以避免与 WEM 数据混淆。

#### Acceptance Criteria

1. THE NEM_Page SHALL 在 Region_Selector 中仅展示 NSW1、QLD1、VIC1、SA1、TAS1 五个区域选项
2. THE NEM_Page SHALL 不包含 WEM 作为可选区域
3. WHEN 用户在 NEM_Page 切换区域, THE NEM_Page SHALL 仅加载对应 NEM 区域的 5 分钟结算间隔数据

### Requirement 3: WEM 页面 ESS 分析

**User Story:** 作为 WEM 市场分析师，我希望在 WEM 页面看到 ESS 辅助服务分析（而非 NEM 的 FCAS），以便评估 WEM 特有的辅助服务收入机会。

#### Acceptance Criteria

1. THE WEM_Page SHALL 展示 ESS 分析模块，包含 Regulation Raise、Regulation Lower、Contingency Raise、Contingency Lower、RoCoF 五种服务类型
2. THE WEM_Page SHALL 不展示 FCAS 分析模块
3. WHEN 用户查看 WEM ESS 分析, THE WEM_Page SHALL 展示各 ESS 类型的价格趋势和收入机会数据
4. WHEN ESS 数据加载失败, THE WEM_Page SHALL 展示包含错误原因和建议操作的错误提示

### Requirement 4: WEM 30 分钟价格间隔

**User Story:** 作为 WEM 市场分析师，我希望价格数据以 30 分钟间隔展示，以匹配 WEM 的实际结算周期。

#### Acceptance Criteria

1. THE WEM_Page SHALL 以 30 分钟间隔展示 RTP 价格数据
2. WHEN WEM_Page 请求价格数据, THE Platform SHALL 在 API 请求中指定 `interval_minutes=30`
3. THE WEM_Page 价格图表的 X 轴 SHALL 以 30 分钟为刻度单位标注时间
4. THE WEM_Page SHALL 使用 AWST（UTC+8）时区展示所有时间标签

### Requirement 5: 侧边栏导航层级

**User Story:** 作为平台用户，我希望在侧边栏导航中看到 NEM 和 WEM 作为同级市场入口，以便理解两者的平等关系并快速切换。

#### Acceptance Criteria

1. THE Sidebar_Navigation SHALL 在"澳洲市场"分组下展示 NEM 和 WEM 作为同级导航项
2. WHEN 用户点击 Sidebar_Navigation 中的 WEM 入口, THE Platform SHALL 导航至 `/wem` 路径
3. WHEN 用户点击 Sidebar_Navigation 中的 NEM 入口, THE Platform SHALL 导航至 `/` 路径
4. WHILE 用户位于 WEM_Page, THE Sidebar_Navigation SHALL 高亮 WEM 导航项为激活状态
5. WHILE 用户位于 NEM_Page, THE Sidebar_Navigation SHALL 高亮 NEM 导航项为激活状态

### Requirement 6: 共享组件复用

**User Story:** 作为开发者，我希望通用分析组件能在 NEM 和 WEM 页面上复用，以减少代码重复并保持一致的用户体验。

#### Acceptance Criteria

1. THE InvestmentAnalysis 组件 SHALL 同时支持在 NEM_Page 和 WEM_Page 中渲染
2. THE DataQualityBadge 组件 SHALL 同时支持在 NEM_Page 和 WEM_Page 中渲染
3. WHEN Shared_Components 在 WEM_Page 中使用, THE Shared_Components SHALL 接收 WEM 市场参数（30 分钟间隔、AWST 时区、AUD 货币）
4. WHEN Shared_Components 在 NEM_Page 中使用, THE Shared_Components SHALL 接收 NEM 市场参数（5 分钟间隔、AEST 时区、AUD 货币）

### Requirement 7: WEM ESS 约束与容量分析

**User Story:** 作为储能投资分析师，我希望在 WEM 页面查看 ESS 约束条件和容量市场分析，以评估 WEM 储能项目的辅助服务和容量收入潜力。

#### Acceptance Criteria

1. THE WEM_Page SHALL 展示 ESS 约束分析模块，显示各 ESS 类型的约束条件和绑定频率
2. THE WEM_Page SHALL 展示容量市场分析模块，显示容量信用和容量价格数据
3. WHEN ESS 约束数据可用, THE WEM_Page SHALL 以图表形式展示约束绑定的时间分布
4. WHEN 容量市场数据可用, THE WEM_Page SHALL 展示容量价格趋势和储能容量信用估算

### Requirement 8: 市场间导航

**User Story:** 作为平台用户，我希望能在 NEM 和 WEM 页面之间便捷切换，以便对比两个市场的投资机会。

#### Acceptance Criteria

1. WHEN 用户位于 NEM_Page, THE NEM_Page SHALL 提供可见的导航入口跳转至 WEM_Page
2. WHEN 用户位于 WEM_Page, THE WEM_Page SHALL 提供可见的导航入口跳转至 NEM_Page
3. WHEN 用户通过页面内导航切换市场, THE Platform SHALL 保持页面切换动画与现有页面过渡一致
4. THE Platform SHALL 支持浏览器前进/后退按钮在 NEM 和 WEM 页面间正确导航

### Requirement 9: WEM 页面设计一致性

**User Story:** 作为平台用户，我希望 WEM 页面遵循与 NEM 页面相同的设计系统，以获得一致的视觉体验和操作习惯。

#### Acceptance Criteria

1. THE WEM_Page SHALL 遵循 DESIGN.md 定义的工业极简设计风格
2. THE WEM_Page SHALL 使用 Playfair Display 字体作为标题、Inter 字体作为正文
3. THE WEM_Page SHALL 使用中文作为主要界面语言，英文术语以括号标注
4. THE WEM_Page SHALL 使用与 NEM_Page 相同的色彩系统（品牌蓝 #0047FF、语义色）
5. THE WEM_Page SHALL 使用与 NEM_Page 相同的组件规范（过滤器按钮、KPI 卡片、Section 标题样式）
