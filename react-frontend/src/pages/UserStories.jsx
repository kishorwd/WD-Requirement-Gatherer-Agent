import { useState, useEffect } from 'react';
import { generateStories } from '../api/client';
import LoadingOverlay from '../components/LoadingOverlay';
import { useProject } from '../context/ProjectContext';

export default function UserStories() {
  const { selectedProjectId, projectDetail } = useProject();

  const [stories, setStories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [generated, setGenerated] = useState(false);

  // Reset when project changes
  useEffect(() => {
    setStories([]);
    setGenerated(false);
    setError('');
  }, [selectedProjectId]);

  const handleGenerate = async () => {
    if (!selectedProjectId) return;
    setError('');
    setLoading(true);
    setStories([]);
    setGenerated(false);
    try {
      const data = await generateStories(selectedProjectId);
      setStories(data);
      setGenerated(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to generate user stories.');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    const headers = ['BRN', 'Module', 'Sub-BRN', 'Sub Module', 'Description', 'Acceptance Criteria'];
    const rows = stories.map((s) => [
      s.brn || '',
      `"${(s.module_name || '').replace(/"/g, '""')}"`,
      s.sub_brn || '',
      `"${(s.sub_module_name || '').replace(/"/g, '""')}"`,
      `"${(s.description || '').replace(/"/g, '""')}"`,
      `"${(s.acceptance_criteria || []).join(' | ').replace(/"/g, '""')}"`,
    ]);
    const csv = [headers, ...rows].map((r) => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `User_Stories_${projectDetail?.client_name || 'Project'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // No project selected prompt
  if (!selectedProjectId) {
    return (
      <div className="page-content fade-in">
        <div className="page-header">
          <span className="page-icon">📝</span>
          <h1>User Story Generator</h1>
          <p>Convert confirmed project requirements into structured user stories with BRN codes and acceptance criteria in GIVEN/WHEN/THEN format.</p>
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
          title="Generating User Stories"
          message="Synthesizing requirements into structured stories..."
          steps={[
            'Fetching project requirements...',
            'Grouping by modules...',
            'Generating story descriptions...',
            'Writing acceptance criteria...',
            'Finalizing BRNs...',
          ]}
          currentStep={2}
        />
      )}

      <div className="page-content fade-in">
        <div className="page-header">
          <span className="page-icon">📝</span>
          <h1>User Story Generator</h1>
          <p>Convert confirmed project requirements into structured user stories with BRN codes and acceptance criteria in GIVEN/WHEN/THEN format.</p>
        </div>

        {error && <div className="alert alert-error mb-lg">{error}</div>}

        {/* Controls */}
        <div className="card mb-xl" style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: '240px' }}>
            <span className="badge badge-info">📁 {projectDetail?.client_name || '...'}</span>
            {projectDetail?.requirement_count > 0 && (
              <span className="badge badge-purple" style={{ marginLeft: '8px' }}>{projectDetail.requirement_count} requirements available</span>
            )}
          </div>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-end' }}>
            <button
              className="btn btn-primary btn-lg"
              onClick={handleGenerate}
              disabled={loading}
            >
              {loading ? <><span className="spinner" /> Generating...</> : '🚀 Generate User Stories'}
            </button>
            {stories.length > 0 && (
              <button className="btn btn-secondary btn-lg" onClick={handleDownload}>
                💾 Download CSV
              </button>
            )}
          </div>
        </div>

        {/* Results */}
        {!generated ? (
          <div className="card" style={{ minHeight: '400px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px' }}>
            <div style={{ fontSize: '3.5rem' }}>📝</div>
            <h3 style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>Click generate to create user stories</h3>
            <p className="text-sm text-muted" style={{ textAlign: 'center', maxWidth: '320px' }}>
              Requirements from all meeting sessions will be synthesized into formatted user stories.
            </p>
          </div>
        ) : stories.length === 0 ? (
          <div className="alert alert-warning">
            No requirements found for this project. Run Post-Meeting Analysis first to populate requirements.
          </div>
        ) : (
          <div className="fade-in">
            {/* Summary bar */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span className="badge badge-success">{stories.length} stories generated</span>
                <span className="badge badge-purple">{new Set(stories.map(s => s.module_name)).size} modules</span>
              </div>
            </div>

            {/* Story Cards */}
            {stories.map((story, i) => (
              <div key={i} className="story-card">
                <div className="story-header">
                  <div>
                    <div className="story-brn">{story.brn} · {story.sub_brn}</div>
                    <div className="story-module">{story.module_name || 'Uncategorized'}</div>
                    <div className="story-submodule">{story.sub_module_name || 'General'}</div>
                  </div>
                  <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                    <span className="badge badge-purple">{story.module_name}</span>
                  </div>
                </div>

                <div className="story-description">{story.description}</div>

                {story.acceptance_criteria?.length > 0 && (
                  <div>
                    <div className="story-criteria-title">Acceptance Criteria</div>
                    {story.acceptance_criteria.map((crit, ci) => (
                      <div key={ci} className="criteria-item">
                        <span className="criteria-dot">✓</span>
                        <span>{crit}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
