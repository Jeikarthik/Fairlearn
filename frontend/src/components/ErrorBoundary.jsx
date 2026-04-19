import { Component } from "react";

/**
 * React error boundary — catches unhandled render/lifecycle errors
 * and shows a recovery UI instead of a blank white screen.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <MyComponent />
 *   </ErrorBoundary>
 *
 * Optional props:
 *   fallback   — custom fallback element
 *   onError    — callback(error, info) for logging / Sentry
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
    this.handleReset = this.handleReset.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary] Caught error:", error, info);
    if (typeof this.props.onError === "function") {
      this.props.onError(error, info);
    }
  }

  handleReset() {
    this.setState({ hasError: false, error: null });
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="error-boundary-container" role="alert">
          <div className="error-boundary-card">
            <h2 className="error-boundary-title">Something went wrong</h2>
            <p className="error-boundary-message">
              {this.state.error?.message || "An unexpected error occurred in this section."}
            </p>
            <div className="error-boundary-actions">
              <button
                className="button-primary"
                onClick={this.handleReset}
                type="button"
              >
                Try again
              </button>
              <button
                className="button-secondary"
                onClick={() => window.location.reload()}
                type="button"
              >
                Reload page
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
