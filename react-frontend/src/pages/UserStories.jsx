import { useState, useEffect, useRef } from 'react';
import { generateStories, getExistingStories } from '../api/client';
import LoadingOverlay from '../components/LoadingOverlay';
import { useProject } from '../context/ProjectContext';

// Agent-themed progress messages that rotate while the backend works
// Covers up to 30+ minutes of processing for large projects
const AGENT_MESSAGES = [
  { message: '📡 Connecting to multi-agent swarm...', step: 0, delay: 0 },
  { message: '📂 Fetching project requirements...', step: 0, delay: 3000 },
  { message: '📦 Grouping requirements by modules...', step: 1, delay: 6000 },
  { message: '🤖 Story Agent is drafting user stories (Module 1)...', step: 2, delay: 10000 },
  { message: '✍️ Writing structured GIVEN/WHEN/THEN descriptions...', step: 2, delay: 25000 },
  { message: '🔍 Agile Coach reviewing Module 1 stories...', step: 3, delay: 45000 },
  { message: '✅ Module 1 approved! Moving to next module...', step: 3, delay: 65000 },
  { message: '🤖 Story Agent drafting Module 2 stories...', step: 2, delay: 85000 },
  { message: '🔍 Agile Coach reviewing Module 2...', step: 3, delay: 110000 },
  { message: '✅ Module 2 approved! Processing next...', step: 3, delay: 135000 },
  { message: '🤖 Story Agent processing Module 3...', step: 2, delay: 160000 },
  { message: '🔍 Agile Coach reviewing Module 3...', step: 3, delay: 190000 },
  { message: '🔁 Processing remaining modules...', step: 3, delay: 220000 },
  { message: '🤖 Story Agent still working... large projects take time...', step: 2, delay: 260000 },
  { message: '🔍 Agile Coach reviewing additional modules...', step: 3, delay: 300000 },
  { message: '⏳ Almost there... reviewing final modules...', step: 4, delay: 360000 },
  { message: '🔄 Multi-Agent loop processing... please be patient...', step: 4, delay: 420000 },
  { message: '📊 Processing large requirement set... still running...', step: 4, delay: 500000 },
  { message: '🔍 Final review cycles in progress...', step: 4, delay: 600000 },
  { message: '⏳ Wrapping up... this is a large project...', step: 5, delay: 720000 },
  { message: '💾 Finalizing and persisting stories...', step: 5, delay: 900000 },
  { message: '🔁 Still processing... the backend is working hard...', step: 5, delay: 1200000 },
  { message: '⏳ Hang tight... almost done...', step: 5, delay: 1500000 },
  { message: '🔁 Large multi-module projects can take 15-30 minutes...', step: 5, delay: 1800000 },
];

export default function UserStories() {
  const { selectedProjectId, projectDetail } = useProject();

  const [stories, setStories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [generated, setGenerated] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [currentStep, setCurrentStep] = useState(0);
  const timersRef = useRef([]);

  // Reset when project changes
  useEffect(() => {
    setStories([]);
    setGenerated(false);
    setError('');

    if (selectedProjectId) {
      loadExistingStories(selectedProjectId);
    }
  }, [selectedProjectId]);

  // Cleanup timers on unmount
  useEffect(() => {
    return () => timersRef.current.forEach(t => clearTimeout(t));
  }, []);

  const loadExistingStories = async (projectId) => {
    setLoading(true);
    try {
      const data = await getExistingStories(projectId);
      if (data && data.length > 0) {
        setStories(data);
        setGenerated(true);
      }
    } catch (err) {
      console.error('Error loading existing stories:', err);
    } finally {
      setLoading(false);
    }
  };

  const startProgressSimulation = () => {
    // Clear any previous timers
    timersRef.current.forEach(t => clearTimeout(t));
    timersRef.current = [];

    AGENT_MESSAGES.forEach(({ message, step, delay }) => {
      const timer = setTimeout(() => {
        setStatusMessage(message);
        setCurrentStep(step);
      }, delay);
      timersRef.current.push(timer);
    });
  };

  const stopProgressSimulation = () => {
    timersRef.current.forEach(t => clearTimeout(t));
    timersRef.current = [];
  };

  const handleGenerate = async () => {
    if (!selectedProjectId) return;
    setError('');
    setLoading(true);
    setStories([]);
    setGenerated(false);
    setStatusMessage('📡 Connecting to multi-agent swarm...');
    setCurrentStep(0);

    // Start the visual progress simulation
    startProgressSimulation();

    try {
      const data = await generateStories(selectedProjectId);
      stopProgressSimulation();
      setStories(data);
      setGenerated(true);
    } catch (err) {
      stopProgressSimulation();
      console.error('Generation error:', err);

      // AUTO-RECOVERY: The backend may have saved stories to DB even if
      // the frontend connection timed out. Check the database first.
      try {
        const savedStories = await getExistingStories(selectedProjectId);
        if (savedStories && savedStories.length > 0) {
          setStories(savedStories);
          setGenerated(true);
          setError('');  // Clear error — we recovered!
          console.log('Auto-recovered %d stories from database', savedStories.length);
          setLoading(false);
          return;
        }
      } catch (recoveryErr) {
        console.error('Recovery check failed:', recoveryErr);
      }

      // If recovery didn't find stories, show the original error
      const detail = err.response?.data?.detail;
      const message = err.message;

      if (detail) {
        setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
      } else if (message) {
        setError(`Network Error: ${message}. The backend may still be processing — try refreshing in a few minutes.`);
      } else {
        setError('An unknown error occurred during story generation.');
      }
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
          message={statusMessage}
          steps={[
            'Fetching project requirements...',
            'Grouping by modules...',
            'Multi-Agent Story Generation...',
            'Agile Coach Review...',
            'Final Approval & Cleanup',
            'Finalizing BRNs...',
          ]}
          currentStep={currentStep}
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
