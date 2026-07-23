// web/src/components/agent/AgentPanel.jsx
// AI Agent workflow orchestration panel — slide-out from right side
import { useState, useCallback } from 'react';
import { runAgentAsync, pollTaskUntilDone, listWorkflows } from '../../lib/agentApi.js';

const WORKFLOW_SHORTCUTS = [
  { id: 'full_investment_feasibility', label: '完整投资分析' },
  { id: 'quick_market_overview', label: '快速市场概览' },
  { id: 'fcas_opportunity', label: 'FCAS 机会' },
  { id: 'risk_assessment', label: '风险评估' },
];

const STATUS_STYLES = {
  completed: { color: '#22C55E', label: '完成' },
  partial: { color: '#F59E0B', label: '部分完成' },
  failed: { color: '#E53E3E', label: '失败' },
  running: { color: '#0047FF', label: '执行中' },
};

export default function AgentPanel({ open, onClose, market = 'NEM', region }) {
  const [query, setQuery] = useState('');
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState('');
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  const executeWorkflow = useCallback(async (workflowId, customQuery) => {
    setRunning(true);
    setProgress('正在提交分析请求...');
    setReport(null);
    setError(null);

    try {
      const params = {
        query: customQuery || query || `运行 ${workflowId} 工作流`,
        market,
        region: region || undefined,
        workflow_template: workflowId || undefined,
        max_steps: 15,
      };

      const { task_id } = await runAgentAsync(params);
      const result = await pollTaskUntilDone(task_id, {
        intervalMs: 2000,
        timeoutMs: 300000,
        onProgress: (msg) => setProgress(msg),
      });

      setReport(result.report);
      setProgress('');
    } catch (err) {
      setError(err.message || '执行失败');
      setProgress('');
    } finally {
      setRunning(false);
    }
  }, [query, market, region]);

  const handleCustomRun = useCallback(() => {
    if (!query.trim()) return;
    executeWorkflow(null, query.trim());
  }, [query, executeWorkflow]);

  if (!open) return null;

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.panel} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={styles.header}>
          <h3 style={styles.title}>AI 分析编排器</h3>
          <button style={styles.closeBtn} onClick={onClose} aria-label="关闭">×</button>
        </div>

        {/* Input */}
        <div style={styles.inputSection}>
          <textarea
            style={styles.textarea}
            placeholder="描述你的分析需求，例如：帮我跑一遍 NSW1 的完整投资可行性分析"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={3}
            disabled={running}
          />
          <button
            style={{ ...styles.runBtn, opacity: running || !query.trim() ? 0.5 : 1 }}
            onClick={handleCustomRun}
            disabled={running || !query.trim()}
          >
            {running ? '执行中...' : '运行分析 / RUN ANALYSIS'}
          </button>
        </div>

        {/* Workflow Shortcuts */}
        <div style={styles.shortcuts}>
          <span style={styles.shortcutLabel}>快捷工作流:</span>
          {WORKFLOW_SHORTCUTS.map((wf) => (
            <button
              key={wf.id}
              style={styles.shortcutBtn}
              onClick={() => executeWorkflow(wf.id)}
              disabled={running}
            >
              {wf.label}
            </button>
          ))}
        </div>

        {/* Progress */}
        {running && progress && (
          <div style={styles.progress}>
            <div style={styles.progressDot} />
            <span>{progress}</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={styles.error}>
            <strong>错误:</strong> {error}
          </div>
        )}

        {/* Report */}
        {report && (
          <div style={styles.report}>
            <ReportView report={report} />
          </div>
        )}
      </div>
    </div>
  );
}

function ReportView({ report }) {
  const statusStyle = STATUS_STYLES[report.status] || STATUS_STYLES.running;

  return (
    <div>
      {/* Status badge */}
      <div style={{ ...styles.statusBadge, borderColor: statusStyle.color }}>
        <span style={{ color: statusStyle.color }}>{statusStyle.label}</span>
        <span style={styles.duration}>{(report.total_duration_ms / 1000).toFixed(1)}s</span>
      </div>

      {/* Executive Summary */}
      {report.executive_summary && (
        <div style={styles.section}>
          <h4 style={styles.sectionTitle}>执行摘要</h4>
          <p style={styles.sectionText}>{report.executive_summary}</p>
        </div>
      )}

      {/* Recommendation */}
      {report.recommendation && (
        <div style={styles.section}>
          <h4 style={styles.sectionTitle}>综合建议</h4>
          <p style={styles.sectionText}>{report.recommendation}</p>
          {report.confidence_level && (
            <span style={styles.confidenceTag}>
              置信度: {report.confidence_level}
            </span>
          )}
        </div>
      )}

      {/* Stage Results */}
      {report.stage_results && report.stage_results.length > 0 && (
        <div style={styles.section}>
          <h4 style={styles.sectionTitle}>分析阶段 ({report.stage_results.length})</h4>
          <div style={styles.stageList}>
            {report.stage_results.map((stage, i) => (
              <div key={i} style={styles.stageItem}>
                <span style={{
                  ...styles.stageDot,
                  backgroundColor: stage.status === 'success' ? '#22C55E' : '#E53E3E',
                }} />
                <span style={styles.stageName}>{stage.tool_name}</span>
                <span style={styles.stageDuration}>{stage.duration_ms?.toFixed(0)}ms</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Risk Flags */}
      {report.risk_flags && report.risk_flags.length > 0 && (
        <div style={styles.section}>
          <h4 style={styles.sectionTitle}>风险标记</h4>
          <ul style={styles.riskList}>
            {report.risk_flags.map((flag, i) => (
              <li key={i} style={styles.riskItem}>{flag}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Data Quality Notes */}
      {report.data_quality_notes && report.data_quality_notes.length > 0 && (
        <div style={styles.section}>
          <h4 style={styles.sectionTitle}>数据质量</h4>
          <ul style={styles.riskList}>
            {report.data_quality_notes.map((note, i) => (
              <li key={i} style={styles.qualityItem}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// --- Styles (inline, following DESIGN.md: industrial minimal, no gradients) ---
const styles = {
  overlay: {
    position: 'fixed',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: 'rgba(0,0,0,0.3)',
    zIndex: 1000,
    display: 'flex',
    justifyContent: 'flex-end',
  },
  panel: {
    width: '480px',
    maxWidth: '90vw',
    height: '100%',
    backgroundColor: '#FFFFFF',
    borderLeft: '1px solid #E5E5E5',
    display: 'flex',
    flexDirection: 'column',
    overflowY: 'auto',
    padding: '24px',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '16px',
  },
  title: {
    fontFamily: "'Inter', sans-serif",
    fontSize: '18px',
    fontWeight: 700,
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
    margin: 0,
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    fontSize: '24px',
    cursor: 'pointer',
    color: '#8E8E8E',
    lineHeight: 1,
  },
  inputSection: {
    marginBottom: '16px',
  },
  textarea: {
    width: '100%',
    padding: '12px',
    border: '1px solid #E5E5E5',
    borderRadius: '8px',
    fontFamily: "'Inter', sans-serif",
    fontSize: '14px',
    resize: 'vertical',
    boxSizing: 'border-box',
  },
  runBtn: {
    marginTop: '8px',
    width: '100%',
    padding: '12px',
    backgroundColor: '#050505',
    color: '#FFFFFF',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    letterSpacing: '0.05em',
  },
  shortcuts: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
    alignItems: 'center',
    marginBottom: '16px',
  },
  shortcutLabel: {
    fontSize: '12px',
    color: '#8E8E8E',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  shortcutBtn: {
    padding: '6px 12px',
    border: '1px solid #E5E5E5',
    borderRadius: '999px',
    background: 'transparent',
    fontSize: '12px',
    cursor: 'pointer',
    fontFamily: "'Inter', sans-serif",
  },
  progress: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '12px',
    backgroundColor: '#F9FAFB',
    borderRadius: '8px',
    fontSize: '14px',
    color: '#050505',
    marginBottom: '16px',
  },
  progressDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    backgroundColor: '#0047FF',
    animation: 'pulse 1.5s infinite',
  },
  error: {
    padding: '12px',
    border: '1px solid #FCA5A5',
    backgroundColor: '#FEF2F2',
    borderRadius: '8px',
    color: '#B91C1C',
    fontSize: '14px',
    marginBottom: '16px',
  },
  report: {
    flex: 1,
  },
  statusBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
    padding: '4px 12px',
    border: '1px solid',
    borderRadius: '999px',
    fontSize: '12px',
    fontWeight: 600,
    marginBottom: '16px',
  },
  duration: {
    color: '#8E8E8E',
    fontWeight: 400,
  },
  section: {
    marginBottom: '16px',
    paddingBottom: '16px',
    borderBottom: '1px solid #F3F4F6',
  },
  sectionTitle: {
    fontFamily: "'Inter', sans-serif",
    fontSize: '12px',
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    color: '#8E8E8E',
    margin: '0 0 8px 0',
  },
  sectionText: {
    fontSize: '14px',
    lineHeight: 1.6,
    color: '#050505',
    margin: 0,
  },
  confidenceTag: {
    display: 'inline-block',
    marginTop: '8px',
    padding: '2px 8px',
    backgroundColor: '#F9FAFB',
    border: '1px solid #E5E5E5',
    borderRadius: '4px',
    fontSize: '12px',
    color: '#8E8E8E',
  },
  stageList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  stageItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '13px',
  },
  stageDot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    flexShrink: 0,
  },
  stageName: {
    flex: 1,
    fontFamily: "'Inter', monospace",
  },
  stageDuration: {
    color: '#8E8E8E',
    fontSize: '12px',
  },
  riskList: {
    margin: 0,
    paddingLeft: '16px',
  },
  riskItem: {
    fontSize: '13px',
    color: '#B91C1C',
    marginBottom: '4px',
  },
  qualityItem: {
    fontSize: '13px',
    color: '#92400E',
    marginBottom: '4px',
  },
};
