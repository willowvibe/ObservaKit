import React, { useState, useEffect, useCallback, createContext, useContext } from 'react';
import {
  Activity,
  CheckCircle,
  AlertTriangle,
  Database,
  Clock,
  TrendingUp,
  ShieldCheck,
  Search,
  RefreshCw,
  BellOff,
  Play,
  XCircle,
  GitBranch,
  Layers,
  ArrowUp,
  FlaskConical,
} from 'lucide-react';
import { mockApiFetch } from './demoData.js';

// ---------------------------------------------------------------------------
// Config & fetch helper
// ---------------------------------------------------------------------------
const API_BASE = import.meta.env.VITE_API_URL || '';
const API_KEY = import.meta.env.VITE_API_KEY || '';

// DemoContext lets every screen know whether to use mock data
const DemoContext = createContext(false);

function useApiFetch() {
  const isDemo = useContext(DemoContext);
  return useCallback((path, opts = {}) => {
    if (isDemo) return mockApiFetch(path);
    return fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(API_KEY ? { 'X-API-Key': API_KEY } : {}) },
      ...opts,
    }).then((res) => {
      if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
      return res.json();
    });
  }, [isDemo]);
}

// Keep the bare apiFetch for the Dashboard shell's own connectivity check
async function apiFetch(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(API_KEY ? { 'X-API-Key': API_KEY } : {}) },
    ...opts,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Shared components
// ---------------------------------------------------------------------------
const StatusBadge = ({ status }) => {
  const config = {
    ok:   { cls: 'badge-ok',   icon: <CheckCircle  size={10} /> },
    warn: { cls: 'badge-warn', icon: <AlertTriangle size={10} /> },
    fail: { cls: 'badge-fail', icon: <XCircle       size={10} /> },
  };
  const { cls, icon } = config[status] || config.ok;
  return (
    <span className={`status-badge ${cls}`}>
      {icon} {status.toUpperCase()}
    </span>
  );
};

const Spinner = () => <span className="spinner" />;

// ---------------------------------------------------------------------------
// Screens
// ---------------------------------------------------------------------------

/** Overview — live /status table grid */
function OverviewScreen() {
  const apiFetch = useApiFetch();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await apiFetch('/status');
      setData(d);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="screen-center"><Spinner /></div>;
  if (error)   return <div className="screen-error">⚠️ {error}</div>;

  const { summary = {}, tables = [], generated_at } = data;

  return (
    <div className="screen">
      <div className="screen-header">
        <h2>Overview</h2>
        <button className="btn-icon" onClick={load} title="Refresh"><RefreshCw size={16} /></button>
      </div>

      {/* Summary tiles */}
      <div className="stat-row">
        {[
          { label: 'Healthy',  value: summary.healthy ?? '—', color: 'green',  icon: <CheckCircle size={20} /> },
          { label: 'Warning',  value: summary.warn    ?? '—', color: 'yellow', icon: <AlertTriangle size={20} /> },
          { label: 'Failing',  value: summary.fail    ?? '—', color: 'red',    icon: <XCircle size={20} /> },
          { label: 'Tables',   value: tables.length,          color: 'blue',   icon: <Database size={20} /> },
        ].map(({ label, value, color, icon }) => (
          <div className={`stat-card stat-${color}`} key={label}>
            <div className="stat-icon">{icon}</div>
            <div className="stat-info">
              <span className="stat-label">{label}</span>
              <span className="stat-value">{value}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Per-table grid */}
      <div className="card">
        <div className="card-header">
          <h3>Table Health Grid</h3>
          <span className="text-muted text-sm">Last updated: {generated_at ? new Date(generated_at).toLocaleTimeString() : '—'}</span>
        </div>
        {tables.length === 0 ? (
          <p className="empty-state">No monitored tables found in the last 24 hours. Start a check run to populate this view.</p>
        ) : (
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Table</th>
                  <th>Freshness</th>
                  <th>Volume</th>
                  <th>Quality</th>
                  <th>Schema</th>
                  <th>Last Checked</th>
                </tr>
              </thead>
              <tbody>
                {tables.map((t) => (
                  <tr key={t.name}>
                    <td className="font-mono">{t.name}</td>
                    <td><StatusBadge status={t.freshness} /></td>
                    <td><StatusBadge status={t.volume} /></td>
                    <td><StatusBadge status={t.quality} /></td>
                    <td><StatusBadge status={t.schema} /></td>
                    <td className="text-muted text-sm">{t.last_checked ? new Date(t.last_checked).toLocaleString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/** Freshness screen — live lag data from /freshness/ */
function FreshnessScreen() {
  const apiFetch = useApiFetch();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/freshness/?limit=100');
      setRecords(Array.isArray(data) ? data : []);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  useEffect(() => { load(); }, [load]);

  const poll = async () => {
    setPolling(true);
    try {
      await apiFetch('/freshness/poll', { method: 'POST' });
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setPolling(false);
    }
  };

  const formatLag = (secs) => {
    if (secs === null || secs === undefined) return '—';
    if (secs < 60)    return `${Math.round(secs)}s`;
    if (secs < 3600)  return `${Math.round(secs / 60)}m`;
    if (secs < 86400) return `${(secs / 3600).toFixed(1)}h`;
    return `${(secs / 86400).toFixed(1)}d`;
  };

  const healthy = records.filter(r => r.status === 'ok').length;
  const warning = records.filter(r => r.status === 'warn').length;
  const failing = records.filter(r => r.status === 'fail').length;

  return (
    <div className="screen">
      <div className="screen-header">
        <h2>Freshness</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-icon" onClick={load} title="Refresh"><RefreshCw size={16} /></button>
          <button className="btn-primary" onClick={poll} disabled={polling}>
            {polling ? <><Spinner /> Polling…</> : <><Play size={14} /> Poll Now</>}
          </button>
        </div>
      </div>

      {error && <div className="screen-error">{error}</div>}

      <div className="stat-row">
        {[
          { label: 'Healthy', value: healthy, color: 'green',  icon: <CheckCircle size={20} /> },
          { label: 'Warning', value: warning, color: 'yellow', icon: <AlertTriangle size={20} /> },
          { label: 'Stale',   value: failing, color: 'red',    icon: <XCircle size={20} /> },
        ].map(({ label, value, color, icon }) => (
          <div className={`stat-card stat-${color}`} key={label}>
            <div className="stat-icon">{icon}</div>
            <div className="stat-info">
              <span className="stat-label">{label}</span>
              <span className="stat-value">{value}</span>
            </div>
          </div>
        ))}
      </div>

      {loading ? <div className="screen-center"><Spinner /></div> : (
        <div className="card">
          <div className="card-header">
            <h3>Table Freshness</h3>
            <span className="text-muted text-sm">{records.length} table{records.length !== 1 ? 's' : ''} tracked</span>
          </div>
          {records.length === 0 ? (
            <p className="empty-state">
              No freshness data yet. Click <strong>Poll Now</strong> to run the first check,
              or add tables under <code>freshness.tables</code> in <code>config/kit.yml</code>.
            </p>
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Table</th>
                    <th>Lag</th>
                    <th>Status</th>
                    <th>Last Checked</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((r, i) => (
                    <tr key={i}>
                      <td className="font-mono">{r.table}</td>
                      <td className={`font-mono lag-cell ${r.status === 'fail' ? 'text-red' : r.status === 'warn' ? 'text-warn' : ''}`}>
                        {r.status !== 'ok' && r.status === 'fail' ? <ArrowUp size={12} style={{ marginRight: 3, verticalAlign: 'middle' }} /> : null}
                        {formatLag(r.lag_seconds)}
                      </td>
                      <td><StatusBadge status={r.status} /></td>
                      <td className="text-muted text-sm">
                        {r.checked_at ? new Date(r.checked_at).toLocaleString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Checks screen — run checks and see results */
function ChecksScreen() {
  const apiFetch = useApiFetch();
  const [results, setResults] = useState([]);
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadResults = useCallback(async () => {
    setLoading(true);
    try {
      const d = await apiFetch('/checks/results?limit=50');
      setResults(d.results || d || []);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  useEffect(() => { loadResults(); }, [loadResults]);

  const runChecks = async () => {
    setRunning(true);
    try {
      await apiFetch('/checks/run', { method: 'POST' });
      await loadResults();
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const failed = results.filter(r => !r.passed);
  const passed = results.filter(r => r.passed);

  return (
    <div className="screen">
      <div className="screen-header">
        <h2>Quality Checks</h2>
        <button className="btn-primary" onClick={runChecks} disabled={running}>
          {running ? <><Spinner /> Running…</> : <><Play size={14} /> Run Now</>}
        </button>
      </div>

      {error && <div className="screen-error">⚠️ {error}</div>}

      <div className="stat-row">
        <div className="stat-card stat-green">
          <div className="stat-icon"><CheckCircle size={20} /></div>
          <div className="stat-info"><span className="stat-label">Passed</span><span className="stat-value">{passed.length}</span></div>
        </div>
        <div className="stat-card stat-red">
          <div className="stat-icon"><XCircle size={20} /></div>
          <div className="stat-info"><span className="stat-label">Failed</span><span className="stat-value">{failed.length}</span></div>
        </div>
      </div>

      {loading ? <div className="screen-center"><Spinner /></div> : (
        <div className="card">
          <div className="card-header"><h3>Recent Results</h3></div>
          {results.length === 0 ? (
            <p className="empty-state">No check results yet. Click "Run Now" to execute your checks.</p>
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead><tr><th>Check</th><th>Table</th><th>Type</th><th>Result</th><th>Details</th><th>Run At</th></tr></thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr key={i}>
                      <td className="font-mono">{r.check_name}</td>
                      <td className="font-mono text-sm">{r.table_name}</td>
                      <td><span className="tag">{r.check_type}</span></td>
                      <td><StatusBadge status={r.passed ? 'ok' : 'fail'} /></td>
                      <td className="text-muted text-sm">{r.details || '—'}</td>
                      <td className="text-muted text-sm">{r.executed_at ? new Date(r.executed_at).toLocaleString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Alerts screen — alert log + suppression controls */
function AlertsScreen() {
  const apiFetch = useApiFetch();
  const [alerts, setAlerts] = useState([]);
  const [suppressions, setSuppressions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [suppTable, setSuppTable] = useState('');
  const [suppMins, setSuppMins] = useState(60);
  const [suppReason, setSuppReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [al, sl] = await Promise.all([
        apiFetch('/webhooks/airflow').catch(() => ({ logs: [] })),
        apiFetch('/suppress/').catch(() => []),
      ]);
      setAlerts(al.logs || []);
      setSuppressions(sl || []);
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  useEffect(() => { load(); }, [load]);

  const createSuppression = async () => {
    if (!suppTable.trim()) return;
    setSubmitting(true);
    try {
      await apiFetch('/suppress/', { method: 'POST', body: JSON.stringify({ table_name: suppTable, duration_minutes: suppMins, reason: suppReason }) });
      setSuppTable(''); setSuppReason(''); setSuppMins(60);
      await load();
    } catch (e) { alert(`Failed: ${e.message}`); }
    setSubmitting(false);
  };

  const deleteSuppression = async (id) => {
    await apiFetch(`/suppress/${id}`, { method: 'DELETE' }).catch(() => {});
    await load();
  };

  return (
    <div className="screen">
      <div className="screen-header">
        <h2>Alerts & Suppressions</h2>
        <button className="btn-icon" onClick={load} title="Refresh"><RefreshCw size={16} /></button>
      </div>

      {loading ? <div className="screen-center"><Spinner /></div> : (<>
        {/* Alert log */}
        <div className="card">
          <div className="card-header">
            <h3>Alert Log</h3>
            <span className="text-muted text-sm">{alerts.length} event{alerts.length !== 1 ? 's' : ''}</span>
          </div>
          {alerts.length === 0 ? (
            <p className="empty-state">No webhook events received yet. Configure the Airflow webhook to stream pipeline alerts here.</p>
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead><tr><th>DAG</th><th>State</th><th>Run ID</th><th>Received At</th></tr></thead>
                <tbody>
                  {alerts.map((a, i) => (
                    <tr key={i}>
                      <td className="font-mono">{a.dag_id || a.dag || '—'}</td>
                      <td><StatusBadge status={a.state === 'success' ? 'ok' : a.state === 'running' ? 'warn' : 'fail'} /></td>
                      <td className="font-mono text-sm text-muted">{a.run_id || '—'}</td>
                      <td className="text-muted text-sm">{a.received_at ? new Date(a.received_at).toLocaleString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Suppression controls */}
        <div className="card">
          <div className="card-header"><h3><BellOff size={16} style={{marginRight:6}} />Suppress Alerts</h3></div>
          <div className="suppress-form">
            <input placeholder="Table (e.g. public.orders)" value={suppTable} onChange={e => setSuppTable(e.target.value)} />
            <input type="number" placeholder="Minutes" value={suppMins} min={1} onChange={e => setSuppMins(Number(e.target.value))} style={{width:90}} />
            <input placeholder="Reason (optional)" value={suppReason} onChange={e => setSuppReason(e.target.value)} />
            <button className="btn-primary" onClick={createSuppression} disabled={submitting}>
              {submitting ? <Spinner /> : 'Suppress'}
            </button>
          </div>

          {suppressions.length > 0 && (
            <div className="table-responsive" style={{marginTop:16}}>
              <table className="data-table">
                <thead><tr><th>Table</th><th>Until</th><th>Reason</th><th></th></tr></thead>
                <tbody>
                  {suppressions.map(s => (
                    <tr key={s.id}>
                      <td className="font-mono">{s.table_name}</td>
                      <td className="text-sm">{new Date(s.suppressed_until).toLocaleString()}</td>
                      <td className="text-muted text-sm">{s.reason || '—'}</td>
                      <td><button className="btn-danger-sm" onClick={() => deleteSuppression(s.id)}>Remove</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </>)}
    </div>
  );
}

/** Profiling screen */
function ProfilingScreen() {
  const apiFetch = useApiFetch();
  const [table, setTable] = useState('');
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [ran, setRan] = useState(false);

  const run = async () => {
    if (!table.trim()) return;
    setLoading(true);
    try {
      const d = await apiFetch(`/profiling/run?table_name=${encodeURIComponent(table)}`, { method: 'POST' });
      setProfiles(d.profiles || []);
      setRan(true);
    } catch (e) { alert(e.message); }
    setLoading(false);
  };

  return (
    <div className="screen">
      <div className="screen-header"><h2>Column Profiling</h2></div>
      <div className="card">
        <div style={{ display:'flex', gap:12, alignItems:'center', marginBottom:12 }}>
          <input placeholder="Table (e.g. public.orders)" value={table} onChange={e => setTable(e.target.value)} style={{flex:1}} />
          <button className="btn-primary" onClick={run} disabled={loading || !table}>
            {loading ? <Spinner /> : <><TrendingUp size={14} /> Profile</>}
          </button>
        </div>
        {ran && profiles.length === 0 && <p className="empty-state">No columns returned.</p>}
        {profiles.length > 0 && (
          <div className="table-responsive">
            <table className="data-table">
              <thead><tr><th>Column</th><th>Null %</th><th>Distinct</th><th>Min</th><th>Max</th></tr></thead>
              <tbody>
                {profiles.map((p, i) => (
                  <tr key={i}>
                    <td className="font-mono">{p.column}</td>
                    <td className={p.null_pct > 10 ? 'text-red' : ''}>{p.null_pct?.toFixed(1)}%</td>
                    <td>{p.distinct_count?.toLocaleString()}</td>
                    <td className="text-muted text-sm">{p.min_value ?? '—'}</td>
                    <td className="text-muted text-sm">{p.max_value ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/** Schema Drift screen — column-level change history */
function SchemaScreen() {
  const apiFetch = useApiFetch();
  const [table, setTable]           = useState('');
  const [diffs, setDiffs]           = useState([]);
  const [loading, setLoading]       = useState(false);
  const [snapshotting, setSnapshotting] = useState(false);
  const [ran, setRan]               = useState(false);
  const [error, setError]           = useState(null);

  const loadDiffs = async () => {
    if (!table.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch(`/schema/diff/${encodeURIComponent(table.trim())}?limit=50`);
      setDiffs(Array.isArray(data) ? data : []);
      setRan(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const takeSnapshot = async () => {
    setSnapshotting(true);
    setError(null);
    try {
      await apiFetch('/schema/snapshot', { method: 'POST' });
      if (table.trim()) await loadDiffs();
    } catch (e) {
      setError(e.message);
    } finally {
      setSnapshotting(false);
    }
  };

  const changeTypeMeta = {
    added:        { cls: 'badge-ok',   label: 'ADDED' },
    removed:      { cls: 'badge-fail', label: 'REMOVED' },
    type_changed: { cls: 'badge-warn', label: 'TYPE CHANGED' },
  };

  return (
    <div className="screen">
      <div className="screen-header">
        <h2>Schema Drift</h2>
        <button className="btn-primary" onClick={takeSnapshot} disabled={snapshotting}>
          {snapshotting ? <><Spinner /> Snapshotting…</> : <><Layers size={14} /> Snapshot All</>}
        </button>
      </div>

      {error && <div className="screen-error">{error}</div>}

      <div className="card">
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12 }}>
          <input
            placeholder="Table name (e.g. public.orders)"
            value={table}
            onChange={e => setTable(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadDiffs()}
            style={{ flex: 1 }}
          />
          <button className="btn-primary" onClick={loadDiffs} disabled={loading || !table.trim()}>
            {loading ? <Spinner /> : <><Search size={14} /> Load Diffs</>}
          </button>
        </div>

        {!ran && (
          <p className="empty-state">
            Enter a table name to view its schema change history, or click <strong>Snapshot All</strong> to capture the current state of all configured tables.
          </p>
        )}
        {ran && diffs.length === 0 && (
          <p className="empty-state">No schema changes detected for <code>{table}</code>. Run a snapshot to establish a baseline.</p>
        )}
        {diffs.length > 0 && (
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Column</th>
                  <th>Change</th>
                  <th>Before</th>
                  <th>After</th>
                  <th>Detected At</th>
                </tr>
              </thead>
              <tbody>
                {diffs.map((d, i) => {
                  const meta = changeTypeMeta[d.change_type] || { cls: 'badge-warn', label: d.change_type?.toUpperCase() };
                  return (
                    <tr key={i}>
                      <td className="font-mono">{d.column_name}</td>
                      <td><span className={`status-badge ${meta.cls}`}>{meta.label}</span></td>
                      <td className="text-muted font-mono text-sm">{d.old_value || '—'}</td>
                      <td className="text-muted font-mono text-sm">{d.new_value || '—'}</td>
                      <td className="text-muted text-sm">
                        {d.detected_at ? new Date(d.detected_at).toLocaleString() : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Dashboard shell
// ---------------------------------------------------------------------------
const TABS = [
  { id: 'overview',   label: 'Overview',         icon: <Activity size={16} />,      key: '1' },
  { id: 'freshness',  label: 'Freshness',         icon: <Clock size={16} />,         key: '2' },
  { id: 'checks',     label: 'Quality Checks',    icon: <ShieldCheck size={16} />,   key: '3' },
  { id: 'schema',     label: 'Schema Drift',      icon: <GitBranch size={16} />,     key: '4' },
  { id: 'alerts',     label: 'Alerts',            icon: <AlertTriangle size={16} />, key: '5' },
  { id: 'profiling',  label: 'Column Profiling',  icon: <TrendingUp size={16} />,    key: '6' },
];

const SCREENS = {
  overview:  OverviewScreen,
  freshness: FreshnessScreen,
  checks:    ChecksScreen,
  schema:    SchemaScreen,
  alerts:    AlertsScreen,
  profiling: ProfilingScreen,
};

const Dashboard = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [backendOk, setBackendOk] = useState(null);

  // backendOk === false after the connectivity probe → switch to demo mode
  const demoMode = backendOk === false;

  useEffect(() => {
    apiFetch('/').then(() => setBackendOk(true)).catch(() => setBackendOk(false));
  }, []);

  // Keyboard shortcuts: 1-6 switch tabs, ignore when typing in inputs
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      const tab = TABS.find(t => t.key === e.key);
      if (tab) setActiveTab(tab.id);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <DemoContext.Provider value={demoMode}>
      <div className="dashboard-container">
        <aside className="sidebar">
          <div className="sidebar-header">
            <Activity size={17} className="sidebar-logo-icon" />
            <h2>ObservaKit</h2>
            <div
              className={`backend-dot ${backendOk === true ? 'dot-ok' : backendOk === false ? 'dot-fail' : 'dot-loading'}`}
              title={backendOk === true ? 'Backend connected' : backendOk === false ? 'Demo mode — no backend' : 'Checking connection…'}
            />
          </div>

          {demoMode && (
            <div className="demo-banner">
              <FlaskConical size={13} />
              Demo mode — sample data
            </div>
          )}

          <nav className="sidebar-nav">
            {TABS.map(tab => (
              <button
                key={tab.id}
                className={`nav-item ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
                title={`${tab.label} (${tab.key})`}
              >
                {tab.icon}
                <span style={{ flex: 1 }}>{tab.label}</span>
                <span className="nav-key-hint">{tab.key}</span>
              </button>
            ))}
          </nav>
          <div className="sidebar-footer">
            <a href={import.meta.env.BASE_URL} className="nav-link-sm">← Home</a>
            <a href="/docs" target="_blank" rel="noreferrer" className="nav-link-sm">API Docs ↗</a>
            <a href="https://github.com/willowvibe/ObservaKit" target="_blank" rel="noreferrer" className="nav-link-sm">GitHub ↗</a>
          </div>
        </aside>

        <main className="dashboard-main">
          {(() => { const Screen = SCREENS[activeTab]; return <Screen />; })()}
        </main>
      </div>
    </DemoContext.Provider>
  );
};

export default Dashboard;
