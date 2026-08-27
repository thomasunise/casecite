import React from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import s from './ErrorBoundary.module.css';

interface ErrorBoundaryProps {
  children: ReactNode;
  /**
   * `page` (default) takes the whole viewport — for the app shell.
   * `inline` renders just the card, so a crashed view leaves the sidebars,
   * header, and navigation working around it.
   */
  variant?: 'page' | 'inline';
  /** Replaces the default "Something went wrong" copy. */
  message?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

/**
 * ErrorBoundary - Catches unhandled render errors in the React component tree
 * and displays a user-friendly fallback UI with CaseCite branding.
 */
class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary] Uncaught error:', error);
    console.error('[ErrorBoundary] Component stack:', errorInfo?.componentStack);
    this.setState({ errorInfo });
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      const inline = this.props.variant === 'inline';
      const card = (
        <div className={s.card} role="alert">
          <div className={s.iconCircle}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--gold-500)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <h1 className={s.title}>Something went wrong</h1>
          <p className={s.message}>
            {this.props.message || 'An unexpected error occurred. Please reload the page to continue.'}
          </p>
          {import.meta.env.DEV && this.state.error && (
            <pre className={s.errorDetail}>
              {this.state.error.toString()}
            </pre>
          )}
          <button className={s.reloadButton} onClick={this.handleReload}>
            Reload
          </button>
        </div>
      );
      if (inline) {
        return (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '32px 16px' }}>
            {card}
          </div>
        );
      }
      return <div className={s.container}>{card}</div>;
    }

    return this.props.children;
  }
}

export { ErrorBoundary };
