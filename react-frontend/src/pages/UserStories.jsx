import { useState, useEffect, useRef, useCallback } from 'react';
import { generateStories, getExistingStories, getClarifications, submitClarificationAnswers } from '../api/client';
import LoadingOverlay from '../components/LoadingOverlay';
import { useProject } from '../context/ProjectContext';

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
  { message: '💾 Finalizing and persisting stories...', step: 5, delay: 600000 },
];

function localKey(projectId) {
  return `hitl_answers_${projectId}`;
}

export default function UserStories() {
  const { selectedProjectId, projectDetail } = useProject();

  const [stories, setStories] = useState([]);
  const [clarifications, setClarifications] = useState([]);
  const [answers, setAnswers] = useState({});  // questionId -> answerText
  const [activeTab, setActiveTab] = useState('stories');  // 'clarifications' | 'stories'
  const [loading, setLoading] = useState(false);
  const [submittingAnswers, setSubmittingAnswers] = useState(false);
  const [generated, setGenerated] = useState(false);
  const [error, setError] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [currentStep, setCurrentStep] = useState(0);
  const timersRef = useRef([]);
  const abortControllerRef = useRef(null);

  const pendingClarifications = clarifications.filter(q => q.status === 'pending');
  const clarificationCount = pendingClarifications.length;

  // Load existing stories + clarifications when project changes
  useEffect(() => {
    setStories([]);
    setGenerated(false);
    setError('');
    setClarifications([]);
    setActiveTab('stories');

    if (selectedProjectId) {
      loadExistingStories(selectedProjectId);
      loadClarifications(selectedProjectId);
      // Restore saved answers from localStorage
      try {
        const saved = localStorage.getItem(localKey(selectedProjectId));
        setAnswers(saved ? JSON.parse(saved) : {});
      } catch {
        setAnswers({});
      }
    } else {
      setAnswers({});
    }
  }, [selectedProjectId]);

  // Auto-switch to clarifications tab if there are pending items
  useEffect(() => {
    if (clarificationCount > 0 && generated) {
      setActiveTab('clarifications');
    }
  }, [clarificationCount, generated]);

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

  const loadClarifications = async (projectId) => {
    try {
      const data = await getClarifications(projectId);
      setClarifications(data || []);
    } catch (err) {
      console.error('Error loading clarifications:', err);
    }
  };

  const startProgressSimulation = () => {
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

  const handleCancelGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    stopProgressSimulation();
    setLoading(false);
    setSubmittingAnswers(false);
    setStatusMessage('');
    setError('Processing was stopped. No data was saved.');
  };

  const handleGenerate = async () => {
    if (!selectedProjectId) return;
    setError('');
    setLoading(true);
    setStories([]);
    setGenerated(false);
    setClarifications([]);
    setStatusMessage('📡 Connecting to multi-agent swarm...');
    setCurrentStep(0);
    startProgressSimulation();

    abortControllerRef.current = new AbortController();
    try {
      const data = await generateStories(selectedProjectId, abortControllerRef.current.signal);
      stopProgressSimulation();
      setStories(data);
      setGenerated(true);
      // Load clarifications separately
      const clars = await getClarifications(selectedProjectId);
      setClarifications(clars || []);
      if (clars && clars.length > 0) {
        setActiveTab('clarifications');
      } else {
        setActiveTab('stories');
      }
    } catch (err) {
      stopProgressSimulation();
      // Aborted by user — error already set in handleCancelGeneration
      if (err.name === 'CanceledError' || err.name === 'AbortError' || err.code === 'ERR_CANCELED') {
        return;
      }
      console.error('Generation error:', err);
      try {
        const savedStories = await getExistingStories(selectedProjectId);
        if (savedStories && savedStories.length > 0) {
          setStories(savedStories);
          setGenerated(true);
          setError('');
          setLoading(false);
          loadClarifications(selectedProjectId);
          return;
        }
      } catch (recoveryErr) {
        console.error('Recovery check failed:', recoveryErr);
      }
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
      abortControllerRef.current = null;
      setLoading(false);
    }
  };

  const handleAnswerChange = (questionId, value) => {
    const updated = { ...answers, [questionId]: value };
    setAnswers(updated);
    // Persist to localStorage
    try {
      localStorage.setItem(localKey(selectedProjectId), JSON.stringify(updated));
    } catch {
      // Storage not available
    }
  };

  const handleSubmitClarifications = async () => {
    const answeredItems = pendingClarifications
      .filter(q => answers[q.id]?.trim())
      .map(q => ({ question_id: q.id, answer_text: answers[q.id].trim() }));

    const unansweredCount = pendingClarifications.length - answeredItems.length;
    if (unansweredCount > 0) {
      const ok = window.confirm(
        `${unansweredCount} question${unansweredCount > 1 ? 's are' : ' is'} unanswered. ` +
        `Regeneration will only cover answered questions. Proceed?`
      );
      if (!ok) return;
    }
    if (answeredItems.length === 0) {
      setError('Please answer at least one question before submitting.');
      return;
    }

    setError('');
    setSubmittingAnswers(true);

    abortControllerRef.current = new AbortController();
    try {
      const result = await submitClarificationAnswers(selectedProjectId, answeredItems, abortControllerRef.current.signal);
      setStories(result.stories || []);
      setClarifications(prev => prev.filter(q => q.status === 'pending' && !answeredItems.find(a => a.question_id === q.id)));
      // Reload actual clarification state from server
      const freshClars = await getClarifications(selectedProjectId);
      setClarifications(freshClars || []);
      // Clear answered items from localStorage
      const remainingAnswers = {};
      (freshClars || []).forEach(q => {
        if (answers[q.id]) remainingAnswers[q.id] = answers[q.id];
      });
      setAnswers(remainingAnswers);
      try {
        localStorage.setItem(localKey(selectedProjectId), JSON.stringify(remainingAnswers));
      } catch { }
      setActiveTab('stories');
    } catch (err) {
      if (err.name === 'CanceledError' || err.name === 'AbortError' || err.code === 'ERR_CANCELED') {
        return;
      }
      const detail = err.response?.data?.detail;
      setError(detail || 'Regeneration failed. Please try again.');
    } finally {
      abortControllerRef.current = null;
      setSubmittingAnswers(false);
    }
  };

  const handleDownload = () => {
    const visibleStories = stories.filter(s => s.generation_status !== 'held');
    const headers = ['BRN', 'Module', 'Sub-BRN', 'Sub Module', 'Description', 'Acceptance Criteria', 'Assumption'];
    const rows = visibleStories.map((s) => [
      s.brn || '',
      `"${(s.module_name || '').replace(/"/g, '""')}"`,
      s.sub_brn || '',
      `"${(s.sub_module_name || '').replace(/"/g, '""')}"`,
      `"${(s.description || '').replace(/"/g, '""')}"`,
      `"${(s.acceptance_criteria || []).join(' | ').replace(/"/g, '""')}"`,
      `"${(s.assumption_text || '').replace(/"/g, '""')}"`,
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

  const convergedStories = stories.filter(s => s.generation_status === 'converged' || !s.generation_status);
  const manualStories = stories.filter(s => s.generation_status === 'manual_required');

  // Group pending clarifications by module for collapsible rendering
  const clarificationsByModule = {};
  pendingClarifications.forEach(q => {
    const mod = q.module_name || 'General';
    if (!clarificationsByModule[mod]) clarificationsByModule[mod] = [];
    clarificationsByModule[mod].push(q);
  });
  const moduleKeys = Object.keys(clarificationsByModule);

  return (
    <>
      {(loading || submittingAnswers) && (
        <LoadingOverlay
          title={submittingAnswers ? 'Regenerating User Stories' : 'Generating User Stories'}
          message={submittingAnswers ? '🔄 Applying your clarifications and updating affected stories...' : statusMessage}
          steps={
            submittingAnswers
              ? ['Applying clarification context...', 'Regenerating held stories...', 'Checking cross-story implications...', 'Updating affected stories...', 'Finalizing BRNs...']
              : ['Fetching project requirements...', 'Grouping by modules...', 'Multi-Agent Story Generation...', 'Agile Coach Review...', 'Final Approval & Cleanup', 'Finalizing BRNs...']
          }
          currentStep={submittingAnswers ? 2 : currentStep}
          onCancel={handleCancelGeneration}
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
              disabled={loading || submittingAnswers}
            >
              {loading ? <><span className="spinner" /> Generating...</> : '🚀 Generate User Stories'}
            </button>
            {convergedStories.length > 0 && (
              <button className="btn btn-secondary btn-lg" onClick={handleDownload} disabled={loading || submittingAnswers}>
                💾 Download CSV
              </button>
            )}
          </div>
        </div>

        {/* Tab Navigation */}
        {generated && (
          <div className="tabs-nav" style={{ marginBottom: '0' }}>
            <button
              className={`tab-btn ${activeTab === 'clarifications' ? 'active' : ''}`}
              onClick={() => setActiveTab('clarifications')}
            >
              ❓ Clarifications Required
              {clarificationCount > 0 && (
                <span className="tab-count-badge">{clarificationCount}</span>
              )}
            </button>
            <button
              className={`tab-btn ${activeTab === 'stories' ? 'active' : ''}`}
              onClick={() => setActiveTab('stories')}
            >
              📋 Generated User Stories
              {convergedStories.length > 0 && (
                <span className="tab-count-badge tab-count-badge--success">{convergedStories.length + manualStories.length}</span>
              )}
            </button>
          </div>
        )}

        {/* ── TAB: Clarifications Required ── */}
        {generated && activeTab === 'clarifications' && (
          <div className="fade-in">
            {clarificationCount === 0 ? (
              <div className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
                <div style={{ fontSize: '2.5rem', marginBottom: '12px' }}>✅</div>
                <h3 style={{ color: 'var(--text-secondary)', fontWeight: 500, marginBottom: '8px' }}>No clarifications needed</h3>
                <p className="text-sm text-muted">All stories were generated successfully. Switch to the Generated User Stories tab to review them.</p>
                <button className="btn btn-secondary" style={{ marginTop: '16px' }} onClick={() => setActiveTab('stories')}>
                  View Generated Stories →
                </button>
              </div>
            ) : (
              <div>
                <div className="card" style={{ marginBottom: '16px', background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.2)' }}>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                    <strong style={{ color: 'var(--text-primary)' }}>{clarificationCount} question{clarificationCount > 1 ? 's' : ''} need{clarificationCount === 1 ? 's' : ''} your input.</strong>{' '}
                    The AI story generator reached its review limit on these items without enough information to proceed confidently.
                    Answer the questions below and submit once — the system will regenerate only the affected stories and check for any knock-on implications across all stories.
                  </p>
                </div>

                {moduleKeys.map((moduleName, moduleIdx) => (
                  <details
                    key={moduleName}
                    open={moduleIdx === 0}
                    className="clarification-section"
                  >
                    <summary className="clarification-section-header">
                      <span className="badge badge-purple" style={{ marginRight: '8px' }}>{moduleName}</span>
                      <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                        {clarificationsByModule[moduleName].length} question{clarificationsByModule[moduleName].length > 1 ? 's' : ''}
                      </span>
                    </summary>

                    <div style={{ padding: '16px 0 8px 0', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                      {clarificationsByModule[moduleName].map((q) => (
                        <div key={q.id} className="clarification-question">
                          <div className="clarification-question-text">{q.question_text}</div>

                          {q.context_text && (
                            <div className="clarification-context">
                              <span style={{ color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Why the AI got stuck: </span>
                              {q.context_text}
                            </div>
                          )}

                          {q.affected_brns?.length > 0 && (
                            <div style={{ marginTop: '8px', display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
                              <span className="text-xs text-muted">Affects:</span>
                              {q.affected_brns.map(brn => (
                                <span key={brn} className="badge badge-default" style={{ fontFamily: 'monospace', fontSize: '0.72rem' }}>{brn}</span>
                              ))}
                            </div>
                          )}

                          <textarea
                            className="clarification-answer"
                            placeholder="Type your answer here…"
                            value={answers[q.id] || ''}
                            onChange={(e) => handleAnswerChange(q.id, e.target.value)}
                            rows={3}
                          />
                        </div>
                      ))}
                    </div>
                  </details>
                ))}

                <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    className="btn btn-primary btn-lg"
                    onClick={handleSubmitClarifications}
                    disabled={submittingAnswers}
                  >
                    {submittingAnswers ? <><span className="spinner" /> Regenerating...</> : '🚀 Submit & Regenerate Stories'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── TAB: Generated User Stories ── */}
        {(!generated || activeTab === 'stories') && (
          <div>
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
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                    <span className="badge badge-success">{convergedStories.length} stories generated</span>
                    <span className="badge badge-purple">{new Set(convergedStories.map(s => s.module_name)).size} modules</span>
                    {manualStories.length > 0 && (
                      <span className="badge badge-warning">{manualStories.length} need manual authoring</span>
                    )}
                    {clarificationCount > 0 && (
                      <span className="badge badge-warning" style={{ cursor: 'pointer' }} onClick={() => setActiveTab('clarifications')}>
                        {clarificationCount} clarification{clarificationCount > 1 ? 's' : ''} pending ↑
                      </span>
                    )}
                  </div>
                </div>

                {/* Manual Required Section */}
                {manualStories.length > 0 && (
                  <div className="manual-required-section">
                    <div className="manual-required-header">
                      ✍️ Needs Manual Authoring ({manualStories.length} stor{manualStories.length > 1 ? 'ies' : 'y'})
                    </div>
                    <p className="text-sm" style={{ color: 'var(--text-muted)', marginBottom: '12px' }}>
                      These stories could not be generated even after clarification. Please author them directly.
                    </p>
                    {manualStories.map((story, i) => (
                      <div key={i} className="story-card story-card--manual">
                        <div className="story-header">
                          <div>
                            <div className="story-brn">{story.brn} · {story.sub_brn}</div>
                            <div className="story-module">{story.module_name || 'Uncategorized'}</div>
                            <div className="story-submodule">{story.sub_module_name || 'General'}</div>
                          </div>
                          <span className="badge badge-warning">Manual Required</span>
                        </div>
                        {story.coach_feedback && (
                          <div className="clarification-context" style={{ marginBottom: '8px' }}>
                            <span style={{ color: 'var(--warning)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Last Coach Feedback: </span>
                            {story.coach_feedback}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Converged Story Cards */}
                {convergedStories.map((story, i) => (
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

                    {story.assumption_text && (
                      <div className="assumption-block">
                        <span className="assumption-label">Assumption:</span> {story.assumption_text}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
