import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import {
  Activity,
  Clock,
  BarChart2,
  CheckSquare,
  GitBranch,
  Zap,
  DollarSign,
  Building2,
  Users,
  LineChart,
  AlertCircle,
  Settings2,
  Award,
  Github,
  LayoutDashboard,
  ArrowRight,
  Check,
  X,
  Minus,
} from 'lucide-react';
import './index.css';
import Dashboard from './dashboard/Dashboard';
import './dashboard/Dashboard.css';

// ---------------------------------------------------------------------------
// Stats Row
// ---------------------------------------------------------------------------
function StatsRow() {
  const stats = [
    { value: '5',    label: 'Observability Pillars' },
    { value: '3+',   label: 'Data Warehouses' },
    { value: '100%', label: 'Self-Hosted' },
    { value: 'MIT',  label: 'Open Source License' },
  ];
  return (
    <div className="stats-row">
      {stats.map((s, i) => (
        <div className="stat-item" key={i}>
          <span className="stat-value">{s.value}</span>
          <span className="stat-desc">{s.label}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Integrations Strip
// ---------------------------------------------------------------------------
function IntegrationsStrip() {
  const warehouses = ['Snowflake', 'BigQuery', 'PostgreSQL', 'Redshift'];
  const tools      = ['Apache Airflow', 'dbt', 'Grafana', 'Prometheus', 'OpenTelemetry'];
  return (
    <div className="integrations-section">
      <p className="integrations-label">Works with</p>
      <div className="integrations-group">
        <span className="integrations-sublabel">Warehouses</span>
        <div className="integrations-chips">
          {warehouses.map(w => <span className="integration-chip" key={w}>{w}</span>)}
        </div>
      </div>
      <div className="integrations-group">
        <span className="integrations-sublabel">Tools</span>
        <div className="integrations-chips">
          {tools.map(t => <span className="integration-chip" key={t}>{t}</span>)}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Comparison Table
// ---------------------------------------------------------------------------
function ComparisonSection() {
  const rows = [
    { feature: 'Freshness Monitoring',     ok: true,  mc: true,  bi: true,  dd: true  },
    { feature: 'Volume Anomaly Detection', ok: true,  mc: true,  bi: true,  dd: 'partial' },
    { feature: 'Quality Checks',           ok: true,  mc: true,  bi: true,  dd: 'partial' },
    { feature: 'Schema Drift',             ok: true,  mc: true,  bi: true,  dd: false },
    { feature: 'Distribution Drift',       ok: true,  mc: true,  bi: false, dd: false },
    { feature: 'Column Profiling',         ok: true,  mc: true,  bi: true,  dd: 'partial' },
    { feature: 'Self-Hosted / On-Prem',    ok: true,  mc: false, bi: false, dd: false },
    { feature: 'Open Source',              ok: true,  mc: false, bi: false, dd: false },
    { feature: 'Pricing',                  ok: 'Free', mc: '$$$$', bi: '$$$$', dd: '$$$$' },
  ];

  const Cell = ({ val }) => {
    if (val === true)  return <span className="cmp-yes"><Check size={14} /></span>;
    if (val === false) return <span className="cmp-no"><X size={14} /></span>;
    if (val === 'partial') return <span className="cmp-partial"><Minus size={14} /></span>;
    return <span className="cmp-text">{val}</span>;
  };

  return (
    <section className="info-section animate-in delay-3">
      <p className="section-label">Why ObservaKit</p>
      <h2>Open source vs. <span className="highlight">closed platforms</span></h2>
      <p className="section-subtitle">
        Get the same core observability as enterprise SaaS tools — without the per-table pricing.
      </p>
      <div className="comparison-wrapper">
        <table className="comparison-table">
          <thead>
            <tr>
              <th>Feature</th>
              <th className="cmp-highlight-col">ObservaKit</th>
              <th>Monte Carlo</th>
              <th>Bigeye</th>
              <th>DataDog</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td>{r.feature}</td>
                <td className="cmp-highlight-col"><Cell val={r.ok} /></td>
                <td><Cell val={r.mc} /></td>
                <td><Cell val={r.bi} /></td>
                <td><Cell val={r.dd} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="comparison-note">
        Partial support ( – ) indicates the feature exists but requires a premium tier or add-on.
      </p>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Nav
// ---------------------------------------------------------------------------
function SiteNav() {
  return (
    <nav className="site-nav">
      <Link to="/" className="nav-logo">
        <Activity size={18} />
        ObservaKit
      </Link>
      <div className="nav-links">
        <a
          href="https://github.com/willowvibe/ObservaKit"
          target="_blank"
          rel="noreferrer"
          className="nav-link"
        >
          GitHub
        </a>
        <Link to="/ui" className="nav-link nav-cta">
          Dashboard
        </Link>
      </div>
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Landing Page
// ---------------------------------------------------------------------------
function LandingPage() {
  const features = [
    {
      icon: <Clock size={18} />,
      title: 'Freshness Monitoring',
      desc: 'Detects stale tables by tracking max(updated_at) and comparing against your SLA thresholds.',
    },
    {
      icon: <BarChart2 size={18} />,
      title: 'Volume Anomaly Detection',
      desc: 'Tracks row counts per table per DAG run with Z-score anomaly detection against a 7-day rolling average.',
    },
    {
      icon: <CheckSquare size={18} />,
      title: 'Quality Checks',
      desc: 'Ships with pre-built Soda Core and Great Expectations templates for null checks, duplicates, and limits.',
    },
    {
      icon: <GitBranch size={18} />,
      title: 'Schema Drift Detector',
      desc: 'Snapshots information_schema and diffs against previous snapshots. Detects added/removed columns.',
    },
    {
      icon: <Zap size={18} />,
      title: 'Pipeline Health',
      desc: 'Pulls Airflow/Prefect metrics via REST API and OpenTelemetry. Pre-built Grafana dashboards included.',
    },
    {
      icon: <DollarSign size={18} />,
      title: 'FinOps Tracker',
      desc: 'Cost observability for Snowflake compute credits and BigQuery bytes billed out-of-the-box.',
    },
  ];

  const useCases = [
    {
      icon: <Building2 size={16} />,
      title: 'Internal Data Platforms',
      desc: 'Stop paying SaaS vendors per-table pricing. Deploy ObservaKit in your VPC to monitor millions of tables securely at zero marginal cost.',
    },
    {
      icon: <Users size={16} />,
      title: 'Agency & Consultancies',
      desc: 'Embed ObservaKit into client deliverables to provide day-one observability guarantees for the ETL pipelines you build for them.',
    },
    {
      icon: <LineChart size={16} />,
      title: 'Analytics Engineering',
      desc: 'Catch schema drift and null-value spikes before they break downstream BI dashboards and erode stakeholder trust.',
    },
  ];

  return (
    <>
      <SiteNav />
      <div className="landing-container">
        {/* Hero */}
        <section className="hero animate-in">
          <div className="badge">v{__APP_VERSION__} · Open Source</div>
          <h1>
            Data Observability
            <br />
            Starter Kit
          </h1>
          <p className="subtitle">
            A self-hosted, Docker-Compose-ready observability layer for small data teams — covering all 5 core pillars without a paid platform.
          </p>
          <div className="cta-container animate-in delay-2">
            <a
              href="https://github.com/willowvibe/ObservaKit"
              className="cta-button"
              target="_blank"
              rel="noreferrer"
            >
              <Github size={15} />
              View on GitHub
            </a>
            <Link to="/ui" className="cta-button secondary">
              <LayoutDashboard size={15} />
              Open Dashboard
            </Link>
          </div>
        </section>

        <StatsRow />

        {/* Features */}
        <section className="section animate-in delay-3">
          <p className="section-label">What's included</p>
          <h2>Five pillars, zero vendor lock-in</h2>
          <p className="section-subtitle">
            Everything your data team needs to monitor pipeline health, detect anomalies, and enforce quality standards.
          </p>
          <div className="features-grid">
            {features.map((f, i) => (
              <div className="feature-card" key={i}>
                <div className="feature-icon">{f.icon}</div>
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </section>

        <IntegrationsStrip />

        {/* How to use */}
        <section className="info-section animate-in delay-3">
          <p className="section-label">Get started</p>
          <h2>Up and running in minutes</h2>
          <p className="section-subtitle">
            Three steps from zero to full observability on your data warehouse.
          </p>
          <div className="steps-container">
            <div className="step-card">
              <div className="step-number">1</div>
              <h3>Clone & Configure</h3>
              <p>
                Clone the repo and copy <code>.env.example</code> to <code>.env</code>. Set your data warehouse credentials.
              </p>
            </div>
            <div className="step-card">
              <div className="step-number">2</div>
              <h3>Spin Up Containers</h3>
              <p>
                Run <code>docker-compose up -d</code>. This launches the FastAPI backend and all required services.
              </p>
            </div>
            <div className="step-card">
              <div className="step-number">3</div>
              <h3>Schedule & Monitor</h3>
              <p>
                Define your SLAs in the config file and view real-time anomalies in the built-in dashboard.
              </p>
            </div>
          </div>
        </section>

        {/* Use cases */}
        <section className="info-section animate-in delay-3">
          <p className="section-label">Use cases</p>
          <h2>Built for teams that ship data</h2>
          <p className="section-subtitle">
            From startup data platforms to enterprise analytics engineering teams.
          </p>
          <div className="usecases-grid">
            {useCases.map((uc, i) => (
              <div className="usecase-item" key={i}>
                <h3>
                  {uc.icon}
                  {uc.title}
                </h3>
                <p>{uc.desc}</p>
              </div>
            ))}
          </div>
        </section>

        <ComparisonSection />

        {/* Case Study */}
        <section className="info-section animate-in delay-3">
          <div className="case-study-section">
            <p className="section-label">Case Study</p>
            <h2>
              The <span className="highlight">$100k</span> Silent Failure
            </h2>
            <p className="cs-lead-text">
              How a mid-sized fintech caught a failing pipeline before it reached the CEO's dashboard.
            </p>

            <div className="cs-grid">
              <div className="cs-card cs-problem">
                <div className="cs-card-header">
                  <AlertCircle size={17} color="#ef4444" />
                  <h3>The Problem</h3>
                </div>
                <p>
                  An upstream API timeout caused their critical <code>transactions</code> ETL pipeline to quietly write <strong>zero rows</strong> overnight.
                </p>
                <div className="cs-metric-box bad">
                  <span className="cs-metric-value">0</span>
                  <span className="cs-metric-label">Rows Written</span>
                </div>
              </div>

              <div className="cs-arrow">
                <ArrowRight size={18} />
              </div>

              <div className="cs-card cs-solution-new">
                <div className="cs-card-header">
                  <Settings2 size={17} color="#6366f1" />
                  <h3>The ObservaKit Solution</h3>
                </div>
                <ul className="cs-feature-list">
                  <li>
                    <strong>Volume Tracking:</strong> Daily row count collection for <code>transactions</code>.
                  </li>
                  <li>
                    <strong>Anomaly Detection:</strong> Z-score algorithm detected a 100% volume drop at 2 AM.
                  </li>
                  <li>
                    <strong>Instant Alert:</strong> Slack notification fired before anyone started their day.
                  </li>
                </ul>
              </div>

              <div className="cs-arrow">
                <ArrowRight size={18} />
              </div>

              <div className="cs-card cs-result-new">
                <div className="cs-card-header">
                  <Award size={17} color="#10b981" />
                  <h3>The Result</h3>
                </div>
                <p>
                  Data Engineering investigated and backfilled the data long before the 9:00 AM executive meeting.
                </p>
                <div className="cs-metric-box good">
                  <span className="cs-metric-value">100%</span>
                  <span className="cs-metric-label">Data Trust Maintained</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <footer className="site-footer">
        <div style={{ marginBottom: '0.625rem' }}>
          <a href="https://www.willowvibe.com" target="_blank" rel="noreferrer">
            <img
              src={`${import.meta.env.BASE_URL}willowvibe-logo.png`}
              alt="WillowVibe Logo"
              height="28"
            />
          </a>
        </div>
        <p style={{ margin: 0 }}>
          Built by{' '}
          <a href="https://www.willowvibe.com" target="_blank" rel="noreferrer">
            WillowVibe DataSynapse
          </a>{' '}
          ·{' '}
          <a href="https://github.com/willowvibe/ObservaKit" target="_blank" rel="noreferrer">
            Open Source on GitHub
          </a>
        </p>
      </footer>
    </>
  );
}

// ---------------------------------------------------------------------------
// App Router
// ---------------------------------------------------------------------------
function App() {
  return (
    <Router basename={import.meta.env.BASE_URL}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/ui" element={<Dashboard />} />
      </Routes>
    </Router>
  );
}

export default App;
