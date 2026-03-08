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
        <div className="badge animate-in">v0.1.2 • Open Source</div>
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

        <section className="info-section animate-in delay-3">
          <h2>How to Use <span className="highlight">ObservaKit</span></h2>
          <div className="steps-container">
            <div className="step-card">
              <div className="step-number">1</div>
              <h3>Clone & Configure</h3>
              <p>Clone the repo and copy <code>.env.example</code> to <code>.env</code>. Set your data warehouse credentials (Snowflake, BigQuery, etc).</p>
            </div>
            <div className="step-card">
              <div className="step-number">2</div>
              <h3>Spin Up Containers</h3>
              <p>Run <code>docker-compose up -d</code>. This launches the FastAPI backend, Postgres metadata DB, Airflow, and Grafana instantly.</p>
            </div>
            <div className="step-card">
              <div className="step-number">3</div>
              <h3>Schedule & Monitor</h3>
              <p>Define your SLAs in the config block and let the scheduler run. View real-time anomalies directly in the pre-built Grafana dashboards.</p>
            </div>
          </div>
        </section>

        <section className="info-section animate-in delay-3">
          <h2>Top Use Cases</h2>
          <div className="usecases-grid">
            <div className="usecase-item">
              <h3>🏢 Internal Data Platforms</h3>
              <p>Stop paying SaaS vendors per-table pricing. Deploy ObservaKit in your VPC to monitor millions of tables securely at zero marginal cost.</p>
            </div>
            <div className="usecase-item">
              <h3>🤝 Agency & Consultancies</h3>
              <p>Embed ObservaKit into client deliverables to provide day-one observability guarantees for the ETL pipelines you build for them.</p>
            </div>
            <div className="usecase-item">
              <h3>🔍 Analytics Engineering</h3>
              <p>Catch schema drift and null-value spikes before they break downstream BI dashboards and erode stakeholder trust.</p>
            </div>
          </div>
        </section>

        <section className="info-section case-study-section animate-in delay-3">
          <h2>Case Study: The <span className="highlight">$100k</span> Silent Failure</h2>
          <p className="cs-lead-text">How a mid-sized fintech caught a failing legagy pipeline before it reached the CEO's dashboard.</p>
          
          <div className="cs-grid">
            {/* The Problem */}
            <div className="cs-card cs-problem">
              <div className="cs-card-header">
                <span className="cs-icon">🚨</span>
                <h3>The Problem</h3>
              </div>
              <p>An upstream API timeout caused their critical <code>transactions</code> ETL pipeline to quietly write <strong>zero rows</strong> overnight.</p>
              <div className="cs-metric-box bad">
                <span className="cs-metric-value">0</span>
                <span className="cs-metric-label">Rows Written</span>
              </div>
              <p className="cs-sub">The pipeline technically "succeeded", silently destroying the integrity of their executive reporting.</p>
            </div>

            {/* Path/Arrow Desktop Only */}
            <div className="cs-arrow">
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </div>

            {/* The Solution */}
            <div className="cs-card cs-solution-new">
              <div className="cs-card-header">
                <span className="cs-icon">⚙️</span>
                <h3>The ObservaKit Solution</h3>
              </div>
              <ul className="cs-feature-list">
                <li>
                  <strong>Volume Tracking:</strong> <span>Daily row count collection for `transactions`.</span>
                </li>
                <li>
                  <strong>Anomaly Detection:</strong> <span>Z-score ML algorithm detected a 100% volume drop vs 7-day avg.</span>
                </li>
                <li>
                  <strong>Instant Alerting:</strong> <span>Fired a high-priority Slack webhook with the Grafana link.</span>
                </li>
              </ul>
              <div className="cs-metric-box neutral">
                <span className="cs-metric-value">&lt; 5 min</span>
                <span className="cs-metric-label">Time to Alert</span>
              </div>
            </div>

            {/* Path/Arrow Desktop Only */}
            <div className="cs-arrow">
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </div>

            {/* The Result */}
            <div className="cs-card cs-result-new">
              <div className="cs-card-header">
                <span className="cs-icon">🏆</span>
                <h3>The Result</h3>
              </div>
              <p>Data Engineering investigated the API timeout and backfilled the data at 8:15 AM—long before the 9:00 AM executive meeting.</p>
              <div className="cs-metric-box good">
                <span className="cs-metric-value">100%</span>
                <span className="cs-metric-label">Data Trust Preserved</span>
              </div>
              <p className="cs-sub">Saved hours of retroactive "what went wrong" meetings and restored confidence in the data team.</p>
            </div>
          </div>
        </section>

      </main>

      <footer className="site-footer">
        <p>Built with ❤️ by Data Engineers, for Data Engineers.</p>
      </footer>
    </>
  )
}

export default App
