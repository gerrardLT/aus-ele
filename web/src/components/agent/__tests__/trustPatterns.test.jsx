/**
 * Agentic 信任模式组件测试（DESIGN-v2.md v1.0 六模式，2026-08-24 落地）
 *
 * 覆盖 web/src/components/agent/ 全部 6 个组件 + 2 个持久化/审计 hook：
 * 1. ConfidenceBadge — 置信度徽章（枚举双档映射，图标双编码）
 * 2. IntentPreview — 意图预览卡（三按钮摩擦点）
 * 3. AutonomyDial + useAutonomyTier — 自主性拨盘（localStorage 持久化）
 * 4. RationalePanel — 推理轨迹折叠面板（默认折叠，sanitized）
 * 5. AuditTimeline + useAuditLog — 操作审计时间线（撤销仅对可逆动作）
 * 6. EscalationCard — 升级路径卡（选项 + 分析师回落）
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, renderHook, act } from '@testing-library/react';
import { StrictMode } from 'react';

import ConfidenceBadge, { CONFIDENCE_LEVEL_MAP } from '../ConfidenceBadge.jsx';
import IntentPreview from '../IntentPreview.jsx';
import AutonomyDial, {
  AUTONOMY_TIERS,
  DEFAULT_AUTONOMY_TIER,
  readAutonomyTier,
  useAutonomyTier,
} from '../AutonomyDial.jsx';
import RationalePanel from '../RationalePanel.jsx';
import AuditTimeline, { useAuditLog } from '../AuditTimeline.jsx';
import EscalationCard from '../EscalationCard.jsx';

// ─── ConfidenceBadge ─────────────────────────────────────────────────────────

describe('ConfidenceBadge', () => {
  it('high → 绿档 ✓ 图标 + 高置信文字双编码', () => {
    render(<ConfidenceBadge level="high" />);
    expect(screen.getByText('✓')).toBeTruthy();
    expect(screen.getByText('高置信')).toBeTruthy();
  });

  it('medium/low → 琥珀档 ? 图标（不伪造数值百分比）', () => {
    const { unmount } = render(<ConfidenceBadge level="medium" />);
    expect(screen.getByText('?')).toBeTruthy();
    expect(screen.getByText('中置信')).toBeTruthy();
    unmount();
    render(<ConfidenceBadge level="low" />);
    expect(screen.getByText('低置信')).toBeTruthy();
  });

  it('未知等级回落中档，不崩溃', () => {
    render(<ConfidenceBadge level="unknown_enum" />);
    expect(screen.getByText('?')).toBeTruthy();
  });

  it('映射表恰好三档且高档唯一', () => {
    const tiers = Object.values(CONFIDENCE_LEVEL_MAP).map((m) => m.tier);
    expect(tiers.filter((t) => t === 'high')).toHaveLength(1);
    expect(Object.keys(CONFIDENCE_LEVEL_MAP)).toHaveLength(3);
  });
});

// ─── IntentPreview ───────────────────────────────────────────────────────────

describe('IntentPreview', () => {
  const setup = () => {
    const onConfirm = vi.fn();
    const onEdit = vi.fn();
    const onCancel = vi.fn();
    render(
      <IntentPreview
        title="导出 PDF 报告"
        steps={['生成快照', '渲染 PDF']}
        notice="导出不可逆"
        onConfirm={onConfirm}
        onEdit={onEdit}
        onCancel={onCancel}
      />,
    );
    return { onConfirm, onEdit, onCancel };
  };

  it('恰好三个动作按钮齐备（继续执行/修改计划/我自己处理）', () => {
    setup();
    expect(screen.getByText('继续执行')).toBeTruthy();
    expect(screen.getByText('修改计划')).toBeTruthy();
    expect(screen.getByText('我自己处理')).toBeTruthy();
  });

  it('mono 编号步骤与不可逆声明渲染', () => {
    setup();
    expect(screen.getByText('生成快照')).toBeTruthy();
    expect(screen.getByText('01')).toBeTruthy();
    expect(screen.getByText('导出不可逆')).toBeTruthy();
  });

  it('三按钮分别触发对应回调', () => {
    const { onConfirm, onEdit, onCancel } = setup();
    fireEvent.click(screen.getByText('继续执行'));
    fireEvent.click(screen.getByText('修改计划'));
    fireEvent.click(screen.getByText('我自己处理'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

// ─── AutonomyDial + useAutonomyTier ─────────────────────────────────────────

describe('AutonomyDial', () => {
  beforeEach(() => {
    globalThis.localStorage.clear();
  });

  it('四档选项齐备且默认「计划需确认」', () => {
    expect(AUTONOMY_TIERS).toHaveLength(4);
    expect(DEFAULT_AUTONOMY_TIER).toBe('plan_confirm');
    expect(readAutonomyTier()).toBe('plan_confirm');
  });

  it('点击切换 aria-pressed 并回调', () => {
    const onChange = vi.fn();
    render(<AutonomyDial value="plan_confirm" onChange={onChange} />);
    const auto = screen.getByText('自动执行');
    expect(auto.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(auto);
    expect(onChange).toHaveBeenCalledWith('auto');
  });

  it('useAutonomyTier 持久化到 localStorage 并惰性读取', () => {
    const { result } = renderHook(() => useAutonomyTier());
    expect(result.current[0]).toBe('plan_confirm');
    act(() => result.current[1]('confirm_exec'));
    expect(result.current[0]).toBe('confirm_exec');
    expect(globalThis.localStorage.getItem('app_autonomy_tier')).toBe('confirm_exec');
    // 新挂载的 hook 读到持久化值
    const second = renderHook(() => useAutonomyTier());
    expect(second.result.current[0]).toBe('confirm_exec');
  });

  it('非法档位被拒绝，脏存储回落默认', () => {
    const { result } = renderHook(() => useAutonomyTier());
    act(() => result.current[1]('bogus_tier'));
    expect(result.current[0]).toBe('plan_confirm');
    globalThis.localStorage.setItem('app_autonomy_tier', 'bogus_tier');
    expect(readAutonomyTier()).toBe('plan_confirm');
  });
});

// ─── RationalePanel ─────────────────────────────────────────────────────────

describe('RationalePanel', () => {
  const trace = [
    { name: 'fetch_prices', status: 'done', durationMs: 1200, summary: '取回 30 天价格', arguments: { secret: 'x' } },
    { name: 'run_backtest', status: 'running' },
  ];

  it('默认折叠，点击展开后展示 sanitized 轨迹（不含 args JSON）', () => {
    render(<RationalePanel trace={trace} />);
    expect(screen.queryByText('fetch_prices')).toBeNull();
    fireEvent.click(screen.getByText('查看推理轨迹'));
    expect(screen.getByText('fetch_prices')).toBeTruthy();
    expect(screen.getByText('✓ 完成')).toBeTruthy();
    expect(screen.queryByText('secret')).toBeNull();
  });

  it('空轨迹不渲染', () => {
    const { container } = render(<RationalePanel trace={[]} />);
    expect(container.firstChild).toBeNull();
  });
});

// ─── AuditTimeline + useAuditLog ────────────────────────────────────────────

describe('AuditTimeline', () => {
  it('撤销按钮仅对可逆动作出现；不可逆动作标注不可逆', () => {
    render(
      <AuditTimeline
        entries={[
          { id: 'a1', time: '10:00:00', action: '清空对话', reversible: true, status: 'done' },
          { id: 'a2', time: '10:01:00', action: '导出 PDF 报告', reversible: false, status: 'done' },
        ]}
        onUndo={() => {}}
      />,
    );
    expect(screen.getByText('撤销')).toBeTruthy();
    expect(screen.getByText('不可逆')).toBeTruthy();
    expect(screen.getAllByText('撤销')).toHaveLength(1);
  });

  it('已撤销条目不再显示撤销按钮', () => {
    render(
      <AuditTimeline
        entries={[{ id: 'a1', time: '10:00:00', action: '清空对话', reversible: true, status: 'undone' }]}
        onUndo={() => {}}
      />,
    );
    expect(screen.queryByText('撤销')).toBeNull();
    expect(screen.getByText('已撤销')).toBeTruthy();
  });

  it('useAuditLog：log 追加条目、undo 仅对可逆 done 条目执行并恢复状态', () => {
    const restore = vi.fn();
    const { result } = renderHook(() => useAuditLog());
    act(() => {
      result.current.log({ action: '清空对话', reversible: true, onUndo: restore });
      result.current.log({ action: '导出 PDF 报告', reversible: false });
    });
    expect(result.current.entries).toHaveLength(2);
    const reversible = result.current.entries.find((e) => e.reversible);
    const irreversible = result.current.entries.find((e) => !e.reversible);
    act(() => {
      result.current.undo(irreversible.id);
    });
    expect(restore).not.toHaveBeenCalled();
    act(() => {
      result.current.undo(reversible.id);
    });
    expect(restore).toHaveBeenCalledTimes(1);
    expect(result.current.entries.find((e) => e.id === reversible.id).status).toBe('undone');
  });

  // 2026-08-24 审查修复守门：undo 副作用必须在 setState updater 外执行，
  // StrictMode 双重调用 updater 时 onUndo 仍只执行一次
  it('StrictMode 下 undo 只执行一次 onUndo（updater 纯函数契约）', () => {
    const restore = vi.fn();
    const wrapper = ({ children }) => <StrictMode>{children}</StrictMode>;
    const { result } = renderHook(() => useAuditLog(), { wrapper });
    act(() => {
      result.current.log({ action: '清空对话', reversible: true, onUndo: restore });
    });
    act(() => {
      result.current.undo(result.current.entries[0].id);
    });
    expect(restore).toHaveBeenCalledTimes(1);
    expect(result.current.entries[0].status).toBe('undone');
  });

  // 2026-08-24 审查修复守门：条目上限防长会话内存无界增长（快照闭包被裁剪释放）
  it('条目超过上限（20）时最旧条目被淘汰', () => {
    const { result } = renderHook(() => useAuditLog());
    act(() => {
      for (let i = 0; i < 25; i++) result.current.log({ action: `动作 ${i}` });
    });
    expect(result.current.entries).toHaveLength(20);
    expect(result.current.entries.at(-1).action).toBe('动作 24');
    expect(result.current.entries[0].action).toBe('动作 5');
  });

  it('撤销失败的条目展示「撤销失败」标记', () => {
    render(
      <AuditTimeline
        entries={[{ id: 'a1', time: '10:00:00', action: '清空对话', reversible: true, status: 'undo_failed' }]}
        onUndo={() => {}}
      />,
    );
    expect(screen.getByText('撤销失败')).toBeTruthy();
    expect(screen.queryByText('撤销')).toBeNull();
  });
});

// ─── EscalationCard ─────────────────────────────────────────────────────────

describe('EscalationCard', () => {
  it('渲染歧义陈述、选项按钮与分析师回落', () => {
    const onResolve = vi.fn();
    const onEscalate = vi.fn();
    render(
      <EscalationCard
        ambiguity="检测到跨市场请求：按 NEM 还是 WEM 口径分析？"
        options={['按 NEM 口径', '按 WEM 口径']}
        onResolve={onResolve}
        onEscalate={onEscalate}
      />,
    );
    expect(screen.getByText(/跨市场请求/)).toBeTruthy();
    fireEvent.click(screen.getByText('按 NEM 口径'));
    expect(onResolve).toHaveBeenCalledWith('按 NEM 口径');
    fireEvent.click(screen.getByText('标记给分析师'));
    expect(onEscalate).toHaveBeenCalledTimes(1);
  });

  it('无选项时仅保留分析师回落，不崩溃', () => {
    render(<EscalationCard ambiguity="数据缺失" options={[]} onResolve={() => {}} onEscalate={() => {}} />);
    expect(screen.getByText('标记给分析师')).toBeTruthy();
  });
});
