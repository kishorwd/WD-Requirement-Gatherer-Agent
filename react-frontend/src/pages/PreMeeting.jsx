import { useState, useEffect, useRef } from 'react';
import FileDropzone from '../components/FileDropzone';
import LoadingOverlay from '../components/LoadingOverlay';
import MarkdownViewer from '../components/MarkdownViewer';
import { generateBrief } from '../api/client';
import { useProject } from '../context/ProjectContext';

const BRIEF_STEPS = [
  'Uploading presales document...',
  'Extracting text from files...',
  'Analyzing with Gemini AI...',
  'Generating discovery questions...',
  'Assembling final brief...',
];

export default function PreMeeting() {
  const { selectedProjectId, projectDetail, refreshProjectDetail } = useProject();

  const [clientName, setClientName] = useState('');
  const [industry, setIndustry] = useState('');
  const [baInput, setBaInput] = useState('');
  const [presalesDoc, setPresalesDoc] = useState(null);
  const [additionalDocs, setAdditionalDocs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [brief, setBrief] = useState(null);
  const [error, setError] = useState('');
  const abortControllerRef = useRef(null);
  const stepTimerRef = useRef(null);

  // Restore state from selected project
  useEffect(() => {
    if (projectDetail) {
      setClientName(projectDetail.client_name || '');
      setIndustry(projectDetail.industry || '');
      if (projectDetail.pre_meeting_brief) {
        setBrief(projectDetail.pre_meeting_brief);
      } else {
        setBrief(null);
      }
    } else {
      setClientName('');
      setIndustry('');
      setBrief(null);
    }
    setError('');
  }, [projectDetail]);

  const addDocSlot = () =>
    setAdditionalDocs((prev) => [...prev, { file: null, explanation: '' }]);

  const updateDoc = (i, field, val) => {
    setAdditionalDocs((prev) => {
      const copy = [...prev];
      copy[i] = { ...copy[i], [field]: val };
      return copy;
    });
  };

  const removeDoc = (i) => setAdditionalDocs((prev) => prev.filter((_, idx) => idx !== i));

  const handleGenerate = async () => {
    if (!clientName.trim()) return setError('Client Name is required.');
    if (!industry.trim()) return setError('Industry is required.');
    if (!presalesDoc) return setError('Presales document is required.');
    setError('');

    const fd = new FormData();
    fd.append('client_name', clientName);
    fd.append('industry', industry);
    fd.append('ba_input', baInput);
    fd.append('presales_doc', presalesDoc);

    for (const doc of additionalDocs) {
      if (doc.file) {
        fd.append('additional_docs', doc.file);
        fd.append('additional_explanations', doc.explanation || '');
      }
    }

    setLoading(true);
    setCurrentStep(0);
    setBrief(null);

    abortControllerRef.current = new AbortController();

    // Simulate step progression
    stepTimerRef.current = setInterval(() => {
      setCurrentStep((s) => (s < BRIEF_STEPS.length - 1 ? s + 1 : s));
    }, 4000);

    try {
      const result = await generateBrief(fd, abortControllerRef.current.signal);
      setBrief(result.brief);
      // Refresh project detail so the sidebar pipeline updates
      refreshProjectDetail();
    } catch (err) {
      if (err.name === 'CanceledError' || err.name === 'AbortError' || err.code === 'ERR_CANCELED') {
        return;
      }
      setError(err.response?.data?.detail || 'Failed to generate brief. Check that backend is running.');
    } finally {
      clearInterval(stepTimerRef.current);
      abortControllerRef.current = null;
      setLoading(false);
      setCurrentStep(0);
    }
  };

  const handleCancelBrief = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    clearInterval(stepTimerRef.current);
    setLoading(false);
    setCurrentStep(0);
    setError('Processing was stopped.');
  };

  const handleDownload = () => {
    const blob = new Blob([brief], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${clientName.replace(/\s+/g, '_')}_Intelligence_Brief.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(brief);
  };

  // No project selected prompt
  if (!selectedProjectId) {
    return (
      <div className="page-content fade-in">
        <div className="page-header">
          <span className="page-icon">🎯</span>
          <h1>Pre-Meeting Intelligence</h1>
          <p>Generate AI-powered briefings before client meetings — including scope analysis, risks, and targeted discovery questions.</p>
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
          title="Generating Intelligence Brief"
          message="This may take 1–3 minutes for large documents..."
          steps={BRIEF_STEPS}
          currentStep={currentStep}
          onCancel={handleCancelBrief}
        />
      )}

      <div className="page-content fade-in">
        {/* Header */}
        <div className="page-header">
          <span className="page-icon">🎯</span>
          <h1>Pre-Meeting Intelligence</h1>
          <p>Generate AI-powered briefings before client meetings — including scope analysis, risks, and targeted discovery questions.</p>
        </div>

        {/* Active project indicator */}
        <div style={{ marginBottom: '20px' }}>
          <span className="badge badge-info">📁 {projectDetail?.client_name || '...'}</span>
          {projectDetail?.industry && (
            <span className="badge badge-purple" style={{ marginLeft: '8px' }}>{projectDetail.industry}</span>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: '24px', alignItems: 'start' }}>
          {/* Left Panel — Inputs */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

            {/* Project Setup */}
            <div className="card">
              <div className="card-title"><span className="card-icon">🏢</span> Project Setup</div>
              <div className="form-group">
                <label className="form-label">Client Name *</label>
                <input
                  className="form-input"
                  placeholder="e.g. Tata Motors"
                  value={clientName}
                  onChange={(e) => setClientName(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Industry *</label>
                <input
                  className="form-input"
                  placeholder="e.g. Automotive Manufacturing"
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                />
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">BA Focus / Context</label>
                <textarea
                  className="form-textarea"
                  placeholder="e.g. Focus on supply chain logistics challenges and EV strategy..."
                  value={baInput}
                  onChange={(e) => setBaInput(e.target.value)}
                  style={{ minHeight: '90px' }}
                />
              </div>
            </div>

            {/* Presales Document */}
            <div className="card">
              <div className="card-title"><span className="card-icon">📎</span> Presales Document *</div>
              <FileDropzone
                label="Drop your SOW / Presales doc"
                subtext="PDF, DOCX, XLSX, XLS supported"
                accept=".pdf,.docx,.xlsx,.xls"
                value={presalesDoc}
                onChange={setPresalesDoc}
                icon="📋"
              />
            </div>

            {/* Additional Documents */}
            <div className="card">
              <div className="card-title" style={{ justifyContent: 'space-between' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="card-icon">📂</span> Additional Docs
                </span>
                <button className="btn btn-ghost btn-sm" onClick={addDocSlot}>+ Add</button>
              </div>
              {additionalDocs.length === 0 && (
                <p className="text-muted text-sm">No additional documents added.</p>
              )}
              {additionalDocs.map((doc, i) => (
                <div key={i} style={{ marginBottom: '16px', paddingBottom: '16px', borderBottom: i < additionalDocs.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <span className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>Document #{i + 1}</span>
                    <button className="btn-ghost btn btn-sm" onClick={() => removeDoc(i)} style={{ color: 'var(--danger)' }}>Remove</button>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Context / Explanation</label>
                    <input
                      className="form-input"
                      placeholder="Describe what this file contains..."
                      value={doc.explanation}
                      onChange={(e) => updateDoc(i, 'explanation', e.target.value)}
                    />
                  </div>
                  <FileDropzone
                    accept=".pdf,.docx,.xlsx,.xls"
                    value={doc.file}
                    onChange={(f) => updateDoc(i, 'file', f)}
                    label="Upload document"
                    subtext="PDF, DOCX, XLSX"
                  />
                </div>
              ))}
            </div>

            {/* Error */}
            {error && (
              <div className="alert alert-error">{error}</div>
            )}

            {/* Generate Button */}
            <button
              className="btn btn-primary btn-lg btn-full"
              onClick={handleGenerate}
              disabled={loading}
            >
              {loading ? <><span className="spinner" /> Generating...</> : brief ? '🔄 Re-Generate Intelligence Brief' : '✨ Generate Intelligence Brief'}
            </button>
          </div>

          {/* Right Panel — Output */}
          <div>
            {!brief ? (
              <div className="card" style={{ minHeight: '500px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px' }}>
                <div style={{ fontSize: '3.5rem' }}>🧠</div>
                <h3 style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>Your brief will appear here</h3>
                <p className="text-sm text-muted" style={{ textAlign: 'center', maxWidth: '300px' }}>
                  Fill in the project details, upload your presales document, and click Generate.
                </p>
              </div>
            ) : (
              <div className="card fade-in">
                {/* Brief Header */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', paddingBottom: '16px', borderBottom: '1px solid var(--border-subtle)' }}>
                  <div>
                    <h2 style={{ marginBottom: '4px' }}>Intelligence Brief</h2>
                    <p className="text-sm text-muted">{clientName} · {industry}</p>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <span className="badge badge-success">Saved ✓</span>
                    <button className="btn btn-secondary btn-sm" onClick={handleCopy}>📋 Copy</button>
                    <button className="btn btn-primary btn-sm" onClick={handleDownload}>⬇️ Download</button>
                  </div>
                </div>
                <MarkdownViewer content={brief} />
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
