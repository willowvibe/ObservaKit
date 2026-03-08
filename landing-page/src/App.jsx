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
          <h2>Case Study: Stopping Silent Legacy ETL Failures</h2>
          <div className="case-study-content">
            <p className="cs-lead"><strong>The Problem:</strong> A mid-sized fintech client had a sprawling legacy ETL pipeline that updated a critical `transactions` table. Due to upstream API timeouts, the pipeline would often write zero rows but still report as "Success", causing massive downstream reporting errors.</p>
            <div className="cs-solution">
              <h4>The ObservaKit Solution:</h4>
              <ul>
                <li><strong>Volume Tracking:</strong> Configured a daily row count tracker for the `transactions` table.</li>
                <li><strong>Anomaly Detection:</strong> ObservaKit's Z-score ML algorithm detected a complete volume cliff compared to the 7-day moving average.</li>
                <li><strong>Immediate Alerting:</strong> Fired a high-priority Slack alert with the Grafana anomaly link within 5 minutes of the ETL run finishing.</li>
              </ul>
            </div>
            <p className="cs-result"><strong>Result:</strong> Data Engineering caught the missing data layer before the 9 AM executive meeting, preserving data trust and saving hours of retroactive data patching.</p>
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
