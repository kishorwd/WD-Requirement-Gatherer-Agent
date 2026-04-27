import { useState } from 'react';

export default function CreateProjectModal({ onClose, onCreate }) {
  const [clientName, setClientName] = useState('');
  const [industry, setIndustry] = useState('');
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!clientName.trim()) return setError('Client Name is required.');
    if (!industry.trim()) return setError('Industry is required.');
    setError('');
    setCreating(true);
    try {
      await onCreate(clientName.trim(), industry.trim());
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create project.');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <h2 style={{ margin: 0 }}>
            <span style={{ marginRight: '8px' }}>🚀</span>
            New Project
          </h2>
          <button
            className="btn btn-ghost btn-sm"
            onClick={onClose}
            style={{ fontSize: '1.2rem', padding: '4px 8px' }}
          >✕</button>
        </div>

        <div className="form-group">
          <label className="form-label">Client Name *</label>
          <input
            className="form-input"
            placeholder="e.g. Tata Motors"
            value={clientName}
            onChange={(e) => setClientName(e.target.value)}
            autoFocus
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Industry *</label>
          <input
            className="form-input"
            placeholder="e.g. Automotive Manufacturing"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          />
        </div>

        {error && <div className="alert alert-error mb-md">{error}</div>}

        <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
          <button className="btn btn-secondary" onClick={onClose} style={{ flex: 1 }}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleCreate}
            disabled={creating}
            style={{ flex: 1 }}
          >
            {creating ? <><span className="spinner" /> Creating...</> : '✨ Create Project'}
          </button>
        </div>
      </div>
    </div>
  );
}
