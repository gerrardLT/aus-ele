import { Component, ReactNode } from 'react';

/**
 * Props type for GlobalErrorBoundary
 * @typedef {Object} Props
 * @property {ReactNode} children - The children to render.
 * @property {(error: Error) => ReactNode} [fallback] - Optional custom fallback component.
 */

/**
 * State type for GlobalErrorBoundary
 * @typedef {Object} State
 * @property {boolean} hasError
 * @property {Error|null} error
 */

/**
 * 全局错误边界（2026-08-24 WQS audit P0）：任何子组件崩溃 → 显示友好提示而非整页白屏
 * @param {{children: ReactNode, fallback?: (error: Error) => ReactNode}} props
 */
export class GlobalErrorBoundary extends Component {
  /** @type {State} */
  state = { hasError: false, error: null };

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error) {
    // 生产环境可接 Sentry/error log
    console.error('[GlobalErrorBoundary]', error.message);
  }

  render() {
    if (this.state.hasError && this.state.error) {
      if (this.props.fallback) return this.props.fallback(this.state.error);
      return (
        <div className="flex min-h-screen flex-col items-center justify-center bg-[var(--color-bg)] px-4 text-center">
          <div className="mx-auto max-w-md rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-sm">
            <h1 className="mb-2 font-serif text-2xl text-[var(--color-text)]">页面出错</h1>
            <p className="mb-4 text-xs text-[var(--color-muted)]">
              非常抱歉，这个页面出错了。您可以点击下面的按钮返回首页重试。
            </p>
            {import.meta.env?.MODE === 'development' && (
              <pre className="mb-4 overflow-auto rounded bg-[var(--color-bg)] p-3 text-[9px] text-[var(--color-error)]">
                {this.state.error?.message}
              </pre>
            )}
            <a
              href="/"
              className="inline-block rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[var(--color-inverted)]"
            >
              ← 返回市场分析
            </a>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
