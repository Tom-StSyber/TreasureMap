import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(err) {
    return { error: err }
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{
          padding: 40, fontFamily: 'monospace', background: '#0f1117',
          color: '#fca5a5', minHeight: '100vh',
        }}>
          <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, color: '#f87171' }}>
            ⚠ TreasureMap crashed on render
          </div>
          <div style={{ marginBottom: 8, color: '#fbbf24' }}>
            {String(this.state.error)}
          </div>
          <pre style={{
            background: '#1e293b', padding: 16, borderRadius: 8,
            fontSize: 12, whiteSpace: 'pre-wrap', color: '#94a3b8',
            overflowX: 'auto',
          }}>
            {this.state.error?.stack}
          </pre>
          <button
            onClick={() => this.setState({ error: null })}
            style={{
              marginTop: 20, padding: '8px 20px', borderRadius: 6,
              background: '#3b82f6', border: 'none', color: '#fff',
              cursor: 'pointer', fontSize: 14,
            }}
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
)
