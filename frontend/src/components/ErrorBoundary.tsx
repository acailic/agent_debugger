import { Component, ErrorInfo, ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, errorInfo: ErrorInfo) => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

/**
 * Error Boundary component for catching React component errors
 * Provides user-friendly fallback UI and optional error reporting
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
    }
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return {
      hasError: true,
      error,
    }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Log to console in development
    if (import.meta.env.DEV) {
      console.error('ErrorBoundary caught an error:', error, errorInfo)
    }

    // Call custom error handler if provided
    this.props.onError?.(error, errorInfo)
  }

  handleRetry = (): void => {
    this.setState({
      hasError: false,
      error: null,
    })
  }

  render(): ReactNode {
    if (this.state.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback
      }

      // Default fallback UI
      return (
        <div className="error-boundary shake-x" role="alert" aria-live="polite">
          <div className="error-boundary-content">
            <span className="error-icon">⚠️</span>
            <h2>Something went wrong</h2>
            <p>{this.state.error?.message ?? 'An unexpected error occurred'}</p>
            {import.meta.env.DEV && this.state.error && (
              <details className="error-details">
                <summary>Error details</summary>
                <pre>{this.state.error.stack}</pre>
              </details>
            )}
            <button
              type="button"
              className="retry-button"
              onClick={this.handleRetry}
            >
              Try again
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
