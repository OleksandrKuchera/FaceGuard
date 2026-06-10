import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** Custom fallback to show instead of the default error screen. */
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error.message, info.componentStack);
  }

  private retry = () => this.setState({ hasError: false, error: undefined });

  render() {
    if (!this.state.hasError) return this.props.children;

    if (this.props.fallback) return this.props.fallback;

    return (
      <div className="flex h-full min-h-[60vh] items-center justify-center">
        <div className="text-center max-w-md px-6">
          <div className="text-4xl mb-4">⚠️</div>
          <p className="text-lg font-semibold text-white mb-2">Щось пішло не так</p>
          <p className="text-sm text-white/40 mb-6 font-mono break-all">
            {this.state.error?.message ?? 'Невідома помилка'}
          </p>
          <button
            onClick={this.retry}
            className="text-sm text-blue-400 hover:text-blue-300 border border-blue-500/30 hover:border-blue-400/50 px-5 py-2 rounded-lg transition-colors"
          >
            Спробувати знову
          </button>
        </div>
      </div>
    );
  }
}
