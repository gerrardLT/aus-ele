export const translations = {
  zh: {
    nav: {
      brand: 'AEMO 澳洲电网智能观测站',
      subtitle: '批发电力市场数据归档',
      toggleOptions: 'EN / 汉'
    },
    header: {
      title1: '澳洲国家',
      title2: '电力市场.',
      description: '一个高保真的极端极简主义工作台。用以观测澳洲电网的高频波动、反向溢价与异常结算报价特征。'
    },
    filters: {
      yearSelect: '年份选择 (YEAR)',
      regionSelect: '区域选择 (REGION)',
      monthSelect: '月份过滤 (MONTH)',
      allMonths: '全年综合',
      quarterSelect: '季度周期 (QUARTER)',
      allQuarters: '无 (ALL)',
      q1: 'Q1 (夏季极值)',
      q2: 'Q2',
      q3: 'Q3 (冬季极值)',
      q4: 'Q4',
      dayTypeSelect: '负荷类型 (DAY TYPE)',
      allDays: '混合 (ALL)',
      weekday: '工作日 (WD)',
      weekend: '周末 (WE)'
    },
    status: {
      loading: '正在扫描数据归档...'
    },
    summary_stats: {
      peak: '峰值价格',
      floor: '绝对谷值',
      mean: '平均价格结算',
    },
    advanced_metrics: {
      title: '特殊量化与极值统计',
      deepDive: '深度挖掘',
      negFreq: '负电价发生概率',
      negMean: '负电价均界',
      negFloor: '绝对负向极值',
      posDays: '缺电溢价天数 (> A$300)',
      posMean: '常规均界',
      posCeiling: '绝对涨停极值',
      floorDays: '极端负溢价穿透天数 (< A$-100)',
      uniqueDays: '发生天数'
    },
    hourly_dist: {
      title: '负电价分布时段 (00:00 - 23:00)',
      incidents: '异常',
      count: '发生频次',
      hourLabel: '发生时段',
      events: '次事件'
    },
    price_chart: {
      time: '时段点',
      noRecords: '当前时间周期暂无记录。'
    },
    cta: {
      message: '发现异常结算行为准则。',
      button: '运行分析'
    }
  },
  
  en: {
    nav: {
      brand: 'AEMO INTELLIGENCE',
      subtitle: 'WHOLESALE ELECTRICITY DATA',
      toggleOptions: '中 / ENG'
    },
    header: {
      title1: 'National',
      title2: 'Electricity Market.',
      description: 'A high-fidelity minimalist workbench exploring the volatility, negative bidding, and settlement prices of the Australian electrical grid.'
    },
    filters: {
      yearSelect: 'YEAR SELECT',
      regionSelect: 'REGION TARGET',
      monthSelect: 'MONTH FILTER',
      allMonths: 'YEAR ROUND',
      quarterSelect: 'QUARTER',
      allQuarters: 'ANY (ALL)',
      q1: 'Q1 (Summer Peak)',
      q2: 'Q2',
      q3: 'Q3 (Winter Peak)',
      q4: 'Q4',
      dayTypeSelect: 'LOAD PROFILE (DAY TYPE)',
      allDays: 'MIXED (ALL)',
      weekday: 'WEEKDAY',
      weekend: 'WEEKEND'
    },
    status: {
      loading: 'Consulting archive...'
    },
    summary_stats: {
      peak: 'Peak Price',
      floor: 'Floor Price',
      mean: 'Mean Settlement'
    },
    advanced_metrics: {
      title: 'Anomalous Bidding Analytics',
      deepDive: 'DEEP DIVE',
      negFreq: 'Negative Frequency',
      negMean: 'Negative Mean',
      negFloor: 'Negative Floor',
      posDays: 'Days > A$300',
      posMean: 'Positive Mean',
      posCeiling: 'Positive Ceiling',
      floorDays: 'Extreme Floor Exceedance (< A$-100)',
      uniqueDays: 'Unique Days'
    },
    hourly_dist: {
      title: 'Negative Price Time Dist. (00:00 - 23:00)',
      incidents: 'Incidents',
      count: 'Count',
      hourLabel: 'HOUR',
      events: 'Events'
    },
    price_chart: {
      time: 'TIME',
      noRecords: 'No records for this temporal frame.'
    },
    cta: {
      message: 'Discover anomalous bidding behaviors.',
      button: 'RUN ANALYSIS'
    }
  }
};
