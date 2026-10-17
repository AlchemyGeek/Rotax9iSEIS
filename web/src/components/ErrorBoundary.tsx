import { Component, type ReactNode } from "react";

// A page that throws while rendering would otherwise unmount the whole app
// (a blank screen on every route until a reload). This catches it, says
// what failed, and clears itself when `resetKey` changes — the router
// passes the current location, so navigating anywhere else recovers.
export class ErrorBoundary extends Component<{ resetKey: string; children: ReactNode }, { error: Error | null; key: string }> {
  state: { error: Error | null; key: string } = { error: null, key: this.props.resetKey };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  static getDerivedStateFromProps(props: { resetKey: string }, state: { error: Error | null; key: string }) {
    return props.resetKey !== state.key ? { error: null, key: props.resetKey } : null;
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" style={{ padding: 48, maxWidth: 640, margin: "0 auto", color: "var(--text-primary)" }}>
        <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>This page hit an error</div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: 12 }}>
          Nothing was saved or lost. If the local server was started before the app was updated, restart it
          (<span className="mono">slingology-eis serve</span>) and reload.
        </div>
        <pre className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)", whiteSpace: "pre-wrap", marginBottom: 16 }}>
          {this.state.error.message}
        </pre>
        <a href="#/flights" style={{ fontSize: 13 }}>Back to Flights</a>
      </div>
    );
  }
}
