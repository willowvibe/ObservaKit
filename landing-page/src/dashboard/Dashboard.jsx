import React, { useState, useEffect } from 'react';
import { 
  Activity, 
  CheckCircle, 
  AlertTriangle, 
  Database, 
  Clock, 
  TrendingUp, 
  ShieldCheck,
  Search,
  ExternalLink
} from 'lucide-react';

const Dashboard = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [healthData, setHealthData] = useState([]);
  const [recentFailures, setRecentFailures] = useState([]);

  // Mock data for initial design - will connect to backend API
  useEffect(() => {
    const fetchData = async () => {
      // In a real app, this would be:
      // const resp = await fetch('http://localhost:8000/checks/results');
      // const data = await resp.json();
      
      const mockHealth = [
        { table: 'public.orders', freshness: 'ok', volume: 'ok', quality: 'fail', last_checked: '10m ago' },
        { table: 'public.order_items', freshness: 'ok', volume: 'ok', quality: 'ok', last_checked: '12m ago' },
        { table: 'reporting.daily_revenue', freshness: 'warn', volume: 'ok', quality: 'ok', last_checked: '1h ago' },
        { table: 'public.customers', freshness: 'ok', volume: 'anomaly', quality: 'ok', last_checked: '5m ago' },
      ];
      
      const mockFailures = [
        { id: 1, table: 'public.orders', check: 'not_null(order_id)', time: '10m ago', severity: 'high' },
        { id: 2, table: 'public.customers', check: 'volume_anomaly', time: '5m ago', severity: 'medium' },
      ];

      setHealthData(mockHealth);
      setRecentFailures(mockFailures);
    };

    fetchData();
  }, []);

  const StatusBadge = ({ status }) => {
    const colors = {
      ok: 'bg-green-500/20 text-green-400 border-green-500/30',
      warn: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
      fail: 'bg-red-500/20 text-red-400 border-red-500/30',
      anomaly: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    };
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs border ${colors[status] || colors.ok}`}>
        {status.toUpperCase()}
      </span>
    );
  };

  return (
    <div className="dashboard-container">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo-spark">🔭</div>
          <h2>ObservaKit v{__APP_VERSION__}</h2>
        </div>
        <nav className="sidebar-nav">
          <button 
            className={`nav-item ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            <Activity size={18} /> Overview
          </button>
          <button 
            className={`nav-item ${activeTab === 'quality' ? 'active' : ''}`}
            onClick={() => setActiveTab('quality')}
          >
            <ShieldCheck size={18} /> Quality Checks
          </button>
          <button 
            className={`nav-item ${activeTab === 'schema' ? 'active' : ''}`}
            onClick={() => setActiveTab('schema')}
          >
            <Database size={18} /> Schema History
          </button>
          <button 
            className={`nav-item ${activeTab === 'alerts' ? 'active' : ''}`}
            onClick={() => setActiveTab('alerts')}
          >
            <AlertTriangle size={18} /> Alert Log
          </button>
        </nav>
      </aside>

      <main className="dashboard-main">
        <header className="dashboard-header">
          <div className="header-search">
            <Search size={18} className="text-muted" />
            <input type="text" placeholder="Search tables, checks..." />
          </div>
          <div className="header-actions">
            <div className="status-indicator">
              <span className="dot pulse"></span> Backend: Online
            </div>
          </div>
        </header>

        <section className="dashboard-content">
          <div className="stats-row">
            <div className="stat-card">
              <div className="stat-icon bg-green-soft"><CheckCircle size={20} /></div>
              <div className="stat-info">
                <span className="stat-label">Passed Checks</span>
                <span className="stat-value">142</span>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon bg-red-soft"><AlertTriangle size={20} /></div>
              <div className="stat-info">
                <span className="stat-label">Active Alerts</span>
                <span className="stat-value">3</span>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon bg-blue-soft"><Clock size={20} /></div>
              <div className="stat-info">
                <span className="stat-label">Avg Freshness</span>
                <span className="stat-value">12m</span>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon bg-purple-soft"><TrendingUp size={20} /></div>
              <div className="stat-info">
                <span className="stat-label">Profiled Columns</span>
                <span className="stat-value">84</span>
              </div>
            </div>
          </div>

          <div className="grid-main">
            <div className="card table-health">
              <div className="card-header">
                <h3>Table Health Overview</h3>
                <button className="btn-text">View All</button>
              </div>
              <div className="table-responsive">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Table Name</th>
                      <th>Freshness</th>
                      <th>Volume</th>
                      <th>Quality</th>
                      <th>Last Sync</th>
                    </tr>
                  </thead>
                  <tbody>
                    {healthData.map((row, i) => (
                      <tr key={i}>
                        <td className="font-mono">{row.table}</td>
                        <td><StatusBadge status={row.freshness} /></td>
                        <td><StatusBadge status={row.volume} /></td>
                        <td><StatusBadge status={row.quality} /></td>
                        <td className="text-muted text-sm">{row.last_checked}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card recent-failures">
              <div className="card-header">
                <h3>Recent Failures</h3>
              </div>
              <div className="failure-list">
                {recentFailures.map(fail => (
                  <div className="failure-item" key={fail.id}>
                    <div className="fail-icon">❌</div>
                    <div className="fail-info">
                      <div className="fail-title">{fail.check}</div>
                      <div className="fail-meta">{fail.table} • {fail.time}</div>
                    </div>
                    <button className="btn-icon">
                      <ExternalLink size={16} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
};

export default Dashboard;
