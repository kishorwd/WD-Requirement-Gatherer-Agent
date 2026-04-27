import { useState, useEffect, useRef } from 'react';
import FileDropzone from '../components/FileDropzone';
import LoadingOverlay from '../components/LoadingOverlay';
import MarkdownViewer from '../components/MarkdownViewer';
import {
  uploadDiscoveryPlan,
  extractSpeakers,
  analyzeTranscript,
  getProjectSessions,
} from '../api/client';
import { useProject } from '../context/ProjectContext';

const SCOPE_BADGE = {
  'In Scope': 'badge-success',
  'Out of Scope': 'badge-danger',
  'Needs Clarification': 'badge-warning',
  'Provisional': 'badge-default',
};

const ROLE_OPTIONS = ['Client', 'BA', 'TS', 'SA', 'Other'];

export default function PostMeeting() {
  const { selectedProjectId, projectDetail, refreshProjectDetail } = useProject();

  const [discoveryFile, setDiscoveryFile] = useState(null);
  const [discoveryUploaded, setDiscoveryUploaded] = useState(false);
  const [transcriptFile, setTranscriptFile] = useState(null);
  const [sessionNumber, setSessionNumber] = useState(1);
  const [speakers, setSpeakers] = useState([]);
  const [speakerTags, setSpeakerTags] = useState({});
  const [loading, setLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState(0);
  const [sessions, setSessions] = useState([]);
  const [uploadingPlan, setUploadingPlan] = useState(false);
  const [extractingSpeakers, setExtractingSpeakers] = useState(false);

  // Restore state when project changes
  useEffect(() => {
    if (projectDetail) {
      // Check if discovery plan is already uploaded
      setDiscoveryUploaded(!!projectDetail.has_discovery_plan);
      // Fetch existing sessions
      if (selectedProjectId) {
        getProjectSessions(selectedProjectId)
          .then((sess) => {
            setSessions(sess);
            // Auto-set session number to next
            if (sess.length > 0) {
              const maxSession = Math.max(...sess.map(s => s.session_number || 0));
              setSessionNumber(maxSession + 1);
            }
            // Restore the latest session result if available
            if (sess.length > 0) {
              const latest = sess[sess.length - 1];
              if (latest.analysis_json) {
                setResult(latest.analysis_json);
                setActiveTab(0);
              }
            }
          })
          .catch(() => {});
      }
    } else {
      // Reset everything
      setDiscoveryUploaded(false);
      setResult(null);
      setSessions([]);
      setSpeakers([]);
      setSpeakerTags({});
      setTranscriptFile(null);
      setDiscoveryFile(null);
      setSessionNumber(1);
    }
    setError('');
  }, [selectedProjectId, projectDetail]);

  // Auto-extract speakers when transcript changes
  useEffect(() => {
    if (!transcriptFile) { setSpeakers([]); setSpeakerTags({}); return; }
    const extract = async () => {
      setExtractingSpeakers(true);
      try {
        const fd = new FormData();
        fd.append('transcript_file', transcriptFile);
        const data = await extractSpeakers(fd);
        const cleaned = (data.speakers || []).filter(
          (s) => typeof s === 'string' && s.trim().length > 1
        );
        setSpeakers(cleaned);
        setSpeakerTags({});
      } catch {
        setSpeakers([]);
      } finally {
        setExtractingSpeakers(false);
      }
    };
    extract();
  }, [transcriptFile]);

  const handleUploadPlan = async () => {
    if (!discoveryFile || !selectedProjectId) return;
    setUploadingPlan(true);
    try {
      const fd = new FormData();
      fd.append('file', discoveryFile);
      await uploadDiscoveryPlan(selectedProjectId, fd);
      setDiscoveryUploaded(true);
      refreshProjectDetail();
    } catch (err) {
      setError('Failed to upload discovery plan: ' + (err.response?.data?.detail || err.message));
    } finally {
      setUploadingPlan(false);
    }
  };

  const toggleSpeaker = (name) => {
    setSpeakerTags((prev) => {
      const copy = { ...prev };
      if (name in copy) { delete copy[name]; }
      else { copy[name] = 'Client'; }
      return copy;
    });
  };

  const handleAnalyze = async () => {
    if (!selectedProjectId || !transcriptFile || !discoveryUploaded) return;
    setError('');
    setLoading(true);
    setLoadingMsg('Uploading transcript...');
    try {
      const fd = new FormData();
      fd.append('project_id', selectedProjectId);
      fd.append('session_number', sessionNumber);
      fd.append('speaker_tags_json', JSON.stringify(speakerTags));
      fd.append('transcript_file', transcriptFile);

      setLoadingMsg('Running AI analysis...');
      const data = await analyzeTranscript(fd);
      setResult(data.analysis_result);
      setActiveTab(0);

      // Fetch sessions for history tab
      const sess = await getProjectSessions(selectedProjectId);
      setSessions(sess);
      // Refresh project detail for pipeline update
      refreshProjectDetail();
    } catch (err) {
      setError(err.response?.data?.detail || 'Analysis failed. Please try again.');
    } finally {
      setLoading(false);
      setLoadingMsg('');
    }
  };

  const canAnalyze = selectedProjectId && discoveryUploaded && transcriptFile;

  const TABS = ['📋 Meeting Summary', '💬 Conversation', '📝 Requirements', '📜 History'];

  // No project selected prompt
  if (!selectedProjectId) {
    return (
      <div className="page-content fade-in">
        <div className="page-header">
          <span className="page-icon">🔍</span>
          <h1>Post-Meeting Analysis</h1>
          <p>Upload meeting transcripts to extract requirements, MoM, on-track/off-track topics, and scope alignment.</p>
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
          title="Analyzing Transcript"
          message={loadingMsg}
          steps={[
            'Uploading transcript file...',
            'Extracting speaker dialogue...',
            'Running AI analysis...',
            'Checking scope alignment...',
            'Building dashboard...',
          ]}
          currentStep={loadingMsg.includes('AI') ? 2 : 0}
        />
      )}

      <div className="page-content fade-in">
        <div className="page-header">
          <span className="page-icon">🔍</span>
          <h1>Post-Meeting Analysis</h1>
          <p>Upload meeting transcripts to extract requirements, MoM, on-track/off-track topics, and scope alignment.</p>
        </div>

        {/* Active project indicator */}
        <div style={{ marginBottom: '20px' }}>
          <span className="badge badge-info">📁 {projectDetail?.client_name || '...'}</span>
          {sessions.length > 0 && (
            <span className="badge badge-purple" style={{ marginLeft: '8px' }}>{sessions.length} session{sessions.length !== 1 ? 's' : ''}</span>
          )}
        </div>

        {error && <div className="alert alert-error mb-lg">{error} <button style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }} onClick={() => setError('')}>✕</button></div>}

        <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '24px', alignItems: 'start' }}>

          {/* Left Setup Panel */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

            {/* 1. Discovery Plan */}
            <div className="card">
              <div className="card-title">
                <span className="card-icon">📋</span> 1. Discovery Plan
                {discoveryUploaded && <span className="badge badge-success" style={{ marginLeft: 'auto' }}>Uploaded ✓</span>}
              </div>
              {discoveryUploaded ? (
                <p className="text-sm text-muted">Discovery plan is already uploaded for this project.</p>
              ) : (
                <>
                  <FileDropzone
                    label="Upload CSV or Excel plan"
                    subtext="CSV, XLSX supported"
                    accept=".csv,.xlsx"
                    value={discoveryFile}
                    onChange={setDiscoveryFile}
                    icon="📊"
                  />
                  {discoveryFile && (
                    <button
                      className="btn btn-secondary btn-full mt-md"
                      onClick={handleUploadPlan}
                      disabled={uploadingPlan}
                    >
                      {uploadingPlan ? <><span className="spinner" /> Uploading...</> : '⬆️ Upload to Backend'}
                    </button>
                  )}
                </>
              )}
            </div>

            {/* 2. Session & Transcript */}
            <div className="card">
              <div className="card-title"><span className="card-icon">🎙️</span> 2. Session & Transcript</div>
              <div className="form-group">
                <label className="form-label">Session Number</label>
                <input
                  type="number"
                  className="form-input"
                  min="1"
                  value={sessionNumber}
                  onChange={(e) => setSessionNumber(Number(e.target.value))}
                />
              </div>
              <FileDropzone
                label="Upload Transcript"
                subtext="TXT, DOCX supported"
                accept=".txt,.docx"
                value={transcriptFile}
                onChange={setTranscriptFile}
                icon="📝"
              />

              {/* Speaker Tagging */}
              {extractingSpeakers && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '12px' }} className="text-sm text-muted">
                  <span className="spinner spinner-accent" style={{ width: '14px', height: '14px', borderWidth: '2px' }} />
                  Detecting speakers...
                </div>
              )}
              {speakers.length > 0 && (
                <div style={{ marginTop: '16px' }}>
                  <div className="section-title">Tag Speakers</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {speakers.map((name) => {
                      const selected = name in speakerTags;
                      return (
                        <div key={name} className={`speaker-tag-card ${selected ? 'selected' : ''}`}>
                          <div className="speaker-avatar">{name[0]}</div>
                          <div style={{ flex: 1 }}>
                            <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{name}</div>
                          </div>
                          {selected ? (
                            <select
                              className="form-select"
                              style={{ width: '100px', padding: '4px 28px 4px 8px', fontSize: '0.8rem' }}
                              value={speakerTags[name]}
                              onChange={(e) => setSpeakerTags((p) => ({ ...p, [name]: e.target.value }))}
                              onClick={(e) => e.stopPropagation()}
                            >
                              {ROLE_OPTIONS.map((r) => <option key={r}>{r}</option>)}
                            </select>
                          ) : null}
                          <button
                            className={`btn btn-sm ${selected ? 'btn-danger' : 'btn-secondary'}`}
                            onClick={() => toggleSpeaker(name)}
                            style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                          >
                            {selected ? '✕' : '+ Tag'}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Analyze Button */}
            <button
              className="btn btn-primary btn-lg btn-full"
              onClick={handleAnalyze}
              disabled={!canAnalyze || loading}
              title={!discoveryUploaded ? 'Upload discovery plan first' : ''}
            >
              {loading ? <><span className="spinner" /> Analyzing...</> : '🚀 Analyze Session'}
            </button>
            {!discoveryUploaded && (
              <p className="text-xs text-muted" style={{ textAlign: 'center' }}>Upload & submit the discovery plan to enable analysis.</p>
            )}
          </div>

          {/* Right Results Panel */}
          <div>
            {!result ? (
              <div className="card" style={{ minHeight: '500px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px' }}>
                <div style={{ fontSize: '3.5rem' }}>🔍</div>
                <h3 style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>Analysis results will appear here</h3>
                <p className="text-sm text-muted" style={{ textAlign: 'center', maxWidth: '320px' }}>
                  Upload a discovery plan and transcript, then click Analyze.
                </p>
              </div>
            ) : (
              <div className="fade-in">
                <div className="tabs-nav">
                  {TABS.map((tab, i) => (
                    <button
                      key={i}
                      className={`tab-btn ${activeTab === i ? 'active' : ''}`}
                      onClick={() => setActiveTab(i)}
                    >
                      {tab}
                    </button>
                  ))}
                </div>

                {/* Tab 0: Meeting Summary */}
                {activeTab === 0 && (
                  <div className="card fade-in">
                    <div className="card-title"><span className="card-icon">📋</span> Minutes of Meeting</div>
                    {Object.keys(speakerTags).length > 0 && (
                      <div className="mom-field">
                        <div className="mom-field-label">Attendees</div>
                        <div className="mom-field-value">
                          {Object.entries(speakerTags).map(([n, r]) => (
                            <span key={n} className="badge badge-default" style={{ marginRight: '6px', marginBottom: '4px' }}>{n} ({r})</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {result.mom ? (
                      <>
                        <div className="mom-html-container" dangerouslySetInnerHTML={{ __html: result.mom }} style={{ color: 'var(--text-primary)', lineHeight: '1.6' }} />
                        <div style={{ marginTop: '16px' }}>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => {
                              const blob = new Blob([`<html data-theme="dark"><head><style>body { font-family: Inter, sans-serif; background: #0f1015; color: #fff; padding: 2rem; max-width: 800px; margin: auto; }</style></head><body>${result.mom}</body></html>`], { type: 'text/html' });
                              const url = URL.createObjectURL(blob);
                              const a = document.createElement('a'); a.href = url; a.download = 'MoM.html'; a.click();
                            }}
                          >⬇️ Download MoM (HTML)</button>
                        </div>
                      </>
                    ) : (
                      <div className="alert alert-warning">No meeting summary generated.</div>
                    )}
                  </div>
                )}

                {/* Tab 1: Conversation Analysis */}
                {activeTab === 1 && (
                  <div className="card fade-in">
                    <div className="card-title"><span className="card-icon">💬</span> Conversation Analysis</div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                      {/* On-Track */}
                      <div>
                        <div className="section-title" style={{ color: 'var(--success)' }}>✅ On-Track Topics</div>
                        {result.on_track_topics_table ? (
                          <MarkdownViewer content={result.on_track_topics_table} />
                        ) : result.on_track_topics?.length ? (
                          <div className="topics-list">
                            {result.on_track_topics.map((t, i) => (
                              <span key={i} className="topic-pill on-track">{t}</span>
                            ))}
                          </div>
                        ) : <p className="text-sm text-muted">No on-track topics identified.</p>}
                      </div>

                      <div className="divider" style={{ margin: '4px 0' }} />

                      {/* Off-Track */}
                      <div>
                        <div className="section-title" style={{ color: 'var(--danger)' }}>❌ Off-Track Topics</div>
                        {result.off_track_topics_table ? (
                          <MarkdownViewer content={result.off_track_topics_table} />
                        ) : result.off_track_topics?.length ? (
                          <div className="topics-list">
                            {result.off_track_topics.map((t, i) => (
                              <span key={i} className="topic-pill off-track">{String(t)}</span>
                            ))}
                          </div>
                        ) : <p className="text-sm text-muted">No off-track topics identified.</p>}
                      </div>

                      <div className="divider" style={{ margin: '4px 0' }} />

                      {/* Open-Ended */}
                      <div>
                        <div className="section-title" style={{ color: 'var(--warning)' }}>❓ Open-Ended Topics</div>
                        {result.open_topics?.length ? (
                          <div className="topics-list">
                            {result.open_topics.map((t, i) => (
                              <span key={i} className="topic-pill open">{String(t)}</span>
                            ))}
                          </div>
                        ) : <p className="text-sm text-muted">No open-ended topics identified.</p>}
                      </div>
                    </div>
                  </div>
                )}

                {/* Tab 2: Requirements */}
                {activeTab === 2 && (
                  <div className="card fade-in">
                    <div className="card-title"><span className="card-icon">📝</span> Provisional Requirements</div>
                    {result.provisional_user_stories?.length ? (
                      <>
                        <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
                          {['In Scope', 'Out of Scope', 'Needs Clarification'].map((s) => {
                            const count = result.provisional_user_stories.filter(r => r.scope_status === s).length;
                            const cls = s === 'In Scope' ? 'badge-success' : s === 'Out of Scope' ? 'badge-danger' : 'badge-warning';
                            return <span key={s} className={`badge ${cls}`}>{s}: {count}</span>;
                          })}
                        </div>
                        <div className="table-container">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>#</th>
                                <th>Requirement</th>
                                <th>Module</th>
                                <th>Scope Status</th>
                                <th>Status</th>
                              </tr>
                            </thead>
                            <tbody>
                              {result.provisional_user_stories.map((req, i) => (
                                <tr key={i}>
                                  <td className="text-xs text-muted">{i + 1}</td>
                                  <td>
                                    <div className="text-primary" style={{ fontSize: '0.875rem', lineHeight: '1.5' }}>{req.text}</div>
                                    {req.scope_justification && (
                                      <div className="text-xs text-muted" style={{ marginTop: '4px' }}>{req.scope_justification}</div>
                                    )}
                                  </td>
                                  <td><span className="badge badge-purple">{req.module || 'General'}</span></td>
                                  <td><span className={`badge ${SCOPE_BADGE[req.scope_status] || 'badge-default'}`}>{req.scope_status || '—'}</span></td>
                                  <td><span className={`badge ${req.status === 'Confirmed' ? 'badge-success' : req.status === 'Rejected' ? 'badge-danger' : 'badge-default'}`}>{req.status || 'Provisional'}</span></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    ) : (
                      <div className="alert alert-warning">No provisional requirements extracted.</div>
                    )}
                  </div>
                )}

                {/* Tab 3: History */}
                {activeTab === 3 && (
                  <div className="card fade-in">
                    <div className="card-title"><span className="card-icon">📜</span> Project Session History</div>
                    {sessions.length ? (
                      <div className="table-container">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Session ID</th>
                              <th>Session #</th>
                              <th>Requirements</th>
                            </tr>
                          </thead>
                          <tbody>
                            {sessions.map((s) => (
                              <tr key={s.id}>
                                <td className="text-muted text-sm">#{s.id}</td>
                                <td className="text-primary">Session {s.session_number}</td>
                                <td className="text-sm text-muted">
                                  {s.analysis_json?.provisional_user_stories?.length || '—'} requirements
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="text-sm text-muted">No previous sessions found for this project.</p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
