import { Component, type ErrorInfo, type PropsWithChildren, type ReactNode } from "react";

interface ErrorBoundaryState {
  failed: boolean;
}

export class ErrorBoundary extends Component<PropsWithChildren, ErrorBoundaryState> {
  state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled application error", error, info);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;

    return (
      <main className="fatal-error">
        <p className="foundation-eyebrow">页面恢复</p>
        <h1>页面暂时无法显示</h1>
        <p>应用遇到了未处理的异常。刷新后会重新恢复登录状态与当前工作区。</p>
        <button type="button" onClick={() => window.location.reload()}>
          刷新页面
        </button>
      </main>
    );
  }
}
