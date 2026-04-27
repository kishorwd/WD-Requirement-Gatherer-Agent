import { useState, useEffect } from 'react';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { getProjectSessions, analyzeScope, getProjectRequirements } from '../api/client';
import LoadingOverlay from '../components/LoadingOverlay';
import { useProject } from '../context/ProjectContext';

const SCOPE_COLORS = {
  'In Scope': '#10b981',
  'Out of Scope': '#ef4444',
  'Needs Clarification': '#f59e0b',
  'Pending Analysis': '#6366f1',
};
const SCOPE_BADGE = {
  'In Scope': 'badge-success',
  'Out of Scope': 'badge-danger',
  'Needs Clarification': 'badge-warning',
};

export default function ScopeGap() {
  const { selectedProjectId, projectDetail, refreshProjectDetail } = useProject();

  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [requirements, setRequirements] = useState([]);
  const [error, setError] = useState('');
  const [analyzed, setAnalyzed] = useState(false);
  const [moduleFilter, setModuleFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');

  // Restore state when project changes
  useEffect(() => {
    if (!selectedProjectId) {
      setSessions([]);
      setRequirements([]);
      setAnalyzed(false);
      return;
    }

    setAnalyzed(false);
    setRequirements([]);
    setModuleFilter('All');
    setStatusFilter('All');

    // Fetch sessions
    getProjectSessions(selectedProjectId).then(setSessions).catch(() => {});

    // Try to load existing requirements (restoring previous analysis)
    getProjectRequirements(selectedProjectId)
      .then((data) => {
        if (data.requirements && data.requirements.length > 0) {
          setRequirements(data.requirements);
          setAnalyzed(true);
        }
      })
      .catch(() => {});
  }, [selectedProjectId]);

  const handleAnalyze = async () => {
    if (!selectedProjectId) return;
    setError('');
    setLoading(true);
    try {
      await analyzeScope(selectedProjectId);
      const data = await getProjectRequirements(selectedProjectId);
      setRequirements(data.requirements || []);
      setAnalyzed(true);
      refreshProjectDetail();
    } catch (err) {
      setError(err.response?.data?.detail || 'Scope analysis failed.');
    } finally {
      setLoading(false);
    }
  };

  // Filtered requirements
  const modules = ['All', ...new Set(requirements.map(r => r.module).filter(Boolean))];
  const statuses = ['All', ...new Set(requirements.map(r => r.scope_status).filter(Boolean))];
  const filtered = requirements.filter((r) => {
    if (moduleFilter !== 'All' && r.module !== moduleFilter) return false;
    if (statusFilter !== 'All' && r.scope_status !== statusFilter) return false;
    return true;
  });

  // Chart data
  const scopeCounts = {};
  requirements.forEach((r) => {
    const s = r.scope_status || 'Pending Analysis';
    scopeCounts[s] = (scopeCounts[s] || 0) + 1;
  });
  const chartData = Object.entries(scopeCounts).map(([name, value]) => ({ name, value }));

  const handleDownload = () => {
    const headers = ['Module', 'Requirement', 'Scope Status', 'Justification'];
    const rows = filtered.map((r) => [
      r.module || '',
      `"${(r.text || '').replace(/"/g, '""')}"`,
      r.scope_status || '',
      `"${(r.scope_justification || '').replace(/"/g, '""')}"`,
    ]);
    const csv = [headers, ...rows].map((r) => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `scope_analysis_${projectDetail?.client_name || 'project'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // No project selected prompt
  if (!selectedProjectId) {
    return (
      <div className="page-content fade-in">
        <div className="page-header">
          <span className="page-icon">📊</span>
          <h1>Scope Gap Analysis</h1>
          <p>Compare all meeting requirements against the Statement of Work to identify scope gaps, out-of-scope items, and ambiguities.</p>
        </div>
        <div className="card no-project-prompt">
          <div className="no-project-icon">📂</div>
          <h3>No project selected</h3>
          <p>Select an existing project or create a new one from the sidebar to get started.</p>
        </div>
      </div>
    );
  }

  return (
    <>
      {loading && (
        <LoadingOverlay
          title="Running Scope Gap Analysis"
          message="Analyzing all meeting transcripts against SOW..."
          steps={[
            'Loading project sessions...',
            'Extracting requirements...',
            'Comparing against SOW...',
            'Consolidating results...',
          ]}
          currentStep={1}
        />
      )}

      <div className="page-content fade-in">
        <div className="page-header">
          <span className="page-icon">📊</span>
          <h1>Scope Gap Analysis</h1>
          <p>Compare all meeting requirements against the Statement of Work to identify scope gaps, out-of-scope items, and ambiguities.</p>
        </div>

        {/* Active project indicator */}
        <div style={{ marginBottom: '20px' }}>
          <span className="badge badge-info">📁 {projectDetail?.client_name || '...'}</span>
          <span className="badge badge-purple" style={{ marginLeft: '8px' }}>{sessions.length} session{sessions.length !== 1 ? 's' : ''}</span>
          {requirements.length > 0 && (
            <span className="badge badge-success" style={{ marginLeft: '8px' }}>{requirements.length} requirements</span>
          )}
        </div>

        {error && <div className="alert alert-error mb-lg">{error}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '24px', alignItems: 'start' }}>

          {/* Left Controls */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className="card">
              <div className="card-title"><span className="card-icon">ℹ️</span> Project Info</div>
              <div style={{ display: 'flex', gap: '12px' }}>
                <div className="stat-card" style={{ flex: 1, padding: '12px', textAlign: 'center' }}>
                  <div className="stat-value" style={{ fontSize: '1.4rem' }}>{sessions.length}</div>
                  <div className="stat-label">Sessions</div>
                </div>
                <div className="stat-card" style={{ flex: 1, padding: '12px', textAlign: 'center' }}>
                  <div className="stat-value" style={{ fontSize: '1.4rem' }}>{requirements.length}</div>
                  <div className="stat-label">Requirements</div>
                </div>
              </div>
            </div>

            {analyzed && requirements.length > 0 && (
              <div className="card">
                <div className="card-title"><span className="card-icon">🔽</span> Filters</div>
                <div className="form-group">
                  <label className="form-label">Module</label>
                  <select className="form-select" value={moduleFilter} onChange={(e) => setModuleFilter(e.target.value)}>
                    {modules.map((m) => <option key={m}>{m}</option>)}
                  </select>
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">Scope Status</label>
                  <select className="form-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                    {statuses.map((s) => <option key={s}>{s}</option>)}
                  </select>
                </div>
              </div>
            )}

            <button
              className="btn btn-primary btn-lg btn-full"
              onClick={handleAnalyze}
              disabled={sessions.length === 0 || loading}
              title={sessions.length === 0 ? 'No sessions found for this project' : ''}
            >
              {loading ? <><span className="spinner" /> Analyzing...</> : analyzed ? '🔄 Re-Run Scope Analysis' : '🔍 Run Scope Analysis'}
            </button>
            {sessions.length === 0 && (
              <p className="text-xs text-muted" style={{ textAlign: 'center' }}>Add meeting sessions in Post-Meeting Analysis first.</p>
            )}
          </div>

          {/* Right Results */}
          <div>
            {!analyzed ? (
              <div className="card" style={{ minHeight: '500px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px' }}>
                <div style={{ fontSize: '3.5rem' }}>📊</div>
                <h3 style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>Run analysis to see results</h3>
                <p className="text-sm text-muted" style={{ textAlign: 'center', maxWidth: '300px' }}>
                  All meeting transcripts will be analyzed against the SOW to classify requirements.
                </p>
              </div>
            ) : (
              <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

                {/* Stats Cards */}
                <div className="stats-grid">
                  <div className="stat-card">
                    <span className="stat-icon">📋</span>
                    <div className="stat-value">{requirements.length}</div>
                    <div className="stat-label">Total</div>
                  </div>
                  <div className="stat-card" style={{ borderColor: 'rgba(16,185,129,0.2)' }}>
                    <span className="stat-icon">✅</span>
                    <div className="stat-value" style={{ color: 'var(--success)' }}>
                      {requirements.filter(r => r.scope_status === 'In Scope').length}
                    </div>
                    <div className="stat-label">In Scope</div>
                  </div>
                  <div className="stat-card" style={{ borderColor: 'rgba(239,68,68,0.2)' }}>
                    <span className="stat-icon">❌</span>
                    <div className="stat-value" style={{ color: 'var(--danger)' }}>
                      {requirements.filter(r => r.scope_status === 'Out of Scope').length}
                    </div>
                    <div className="stat-label">Out of Scope</div>
                  </div>
                  <div className="stat-card" style={{ borderColor: 'rgba(245,158,11,0.2)' }}>
                    <span className="stat-icon">❓</span>
                    <div className="stat-value" style={{ color: 'var(--warning)' }}>
                      {requirements.filter(r => r.scope_status === 'Needs Clarification').length}
                    </div>
                    <div className="stat-label">Needs Clarification</div>
                  </div>
                </div>

                {/* Chart + Table */}
                <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '20px', alignItems: 'start' }}>
                  {chartData.length > 0 && (
                    <div className="card" style={{ padding: '16px' }}>
                      <div className="card-title"><span className="card-icon">🥧</span> Distribution</div>
                      <ResponsiveContainer width="100%" height={220}>
                        <PieChart>
                          <Pie data={chartData} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, percent }) => `${(percent * 100).toFixed(0)}%`} labelLine={false}>
                            {chartData.map((entry, index) => (
                              <Cell key={index} fill={SCOPE_COLORS[entry.name] || '#6366f1'} />
                            ))}
                          </Pie>
                          <Tooltip
                            contentStyle={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '8px', fontSize: '0.8rem' }}
                          />
                          <Legend iconSize={10} wrapperStyle={{ fontSize: '0.75rem', color: 'var(--text-muted)' }} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                      <span className="text-sm text-muted">{filtered.length} requirements</span>
                      <button className="btn btn-secondary btn-sm" onClick={handleDownload}>⬇️ Download CSV</button>
                    </div>
                    <div className="table-container">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Status</th>
                            <th>Module</th>
                            <th>Requirement</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filtered.map((r, i) => (
                            <tr key={i}>
                              <td><span className={`badge ${SCOPE_BADGE[r.scope_status] || 'badge-default'}`}>{r.scope_status || '—'}</span></td>
                              <td><span className="badge badge-purple">{r.module || 'General'}</span></td>
                              <td>
                                <div className="text-primary" style={{ fontSize: '0.85rem', lineHeight: '1.5' }}>{r.text}</div>
                                {r.scope_justification && (
                                  <div className="text-xs text-muted" style={{ marginTop: '3px' }}>{r.scope_justification}</div>
                                )}
                              </td>
                            </tr>
                          ))}
                          {filtered.length === 0 && (
                            <tr><td colSpan={3} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px' }}>No results match the filters.</td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
