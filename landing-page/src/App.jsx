import './index.css'

function App() {
  const features = [
    {
      title: "Freshness Monitoring",
      icon: "🕐",
      desc: "Detects stale tables by tracking max(updated_at) and comparing against your SLA thresholds."
    },
    {
      title: "Volume Anomaly Detection",
      icon: "📊",
      desc: "Tracks row counts per table per DAG run with Z-score anomaly detection against a 7-day rolling average."
    },
    {
      title: "Quality Checks",
      icon: "✅",
      desc: "Ships with pre-built Soda Core and Great Expectations templates for null checks, duplicates, and limits."
    },
    {
      title: "Schema Drift Detector",
      icon: "🔀",
      desc: "Snapshots information_schema and diffs against previous snapshots. Detects added/removed columns."
    },
    {
      title: "Pipeline Health",
      icon: "🚀",
      desc: "Pulls Airflow/Prefect metrics via REST API and OpenTelemetry. Pre-built Grafana dashboards."
    },
    {
      title: "FinOps Tracker",
      icon: "💸",
      desc: "Cost observability for Snowflake compute credits and BigQuery bytes billed out-of-the-box."
    }
  ];

  return (
    <>
      <main>
        <div className="badge animate-in">v0.1.0 • Open Source</div>
        <h1 className="animate-in delay-1">Data Observability<br />Starter Kit</h1>
        <p className="subtitle animate-in delay-2">
          A self-hosted, Docker-Compose-ready observability layer that gives small data teams the 5 core observability pillars without needing a paid platform.
        </p>
        
        <a href="https://github.com/willowvibe/ObservaKit" className="cta-button animate-in delay-3" target="_blank" rel="noreferrer">
          View on GitHub
        </a>

        <div className="features-grid animate-in delay-3">
          {features.map((f, i) => (
            <div className="feature-card" key={i}>
              <h3><span style={{fontSize: '1.5rem'}}>{f.icon}</span> {f.title}</h3>
              <p>{f.desc}</p>
            </div>
          ))}
        </div>
      </main>
    </>
  )
}

export default App
