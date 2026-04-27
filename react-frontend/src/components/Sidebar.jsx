import { NavLink } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { checkHealth } from '../api/client';
import { useProject } from '../context/ProjectContext';
import CreateProjectModal from './CreateProjectModal';
import '../styles/components.css';

const navItems = [
  { to: '/', icon: '🎯', label: 'Pre-Meeting Intelligence', exact: true },
  { to: '/post-meeting', icon: '🔍', label: 'Post-Meeting Analysis' },
  { to: '/scope-gap', icon: '📊', label: 'Scope Gap Analysis' },
  { to: '/user-stories', icon: '📝', label: 'User Story Generator' },
];

const PIPELINE_STEPS = [
  { key: 'brief', label: 'Pre-Meeting Brief', check: (p) => p?.has_brief },
  { key: 'sessions', label: 'Meeting Sessions', check: (p) => p?.session_count > 0 },
  { key: 'requirements', label: 'Requirements', check: (p) => p?.requirement_count > 0 },
];

export default function Sidebar() {
  const [online, setOnline] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const {
    projects,
    selectedProjectId,
    projectDetail,
    selectProject,
    createAndSelectProject,
    deleteProject,
  } = useProject();

  useEffect(() => {
    const check = async () => {
      const ok = await checkHealth();
      setOnline(ok);
    };
    check();
    const interval = setInterval(check, 15000);
    return () => clearInterval(interval);
  }, []);

  // Find the summary for selected project (from list data)
  const selectedSummary = projects.find((p) => p.id === selectedProjectId);

  const handleDelete = async () => {
    if (!selectedProjectId) return;
    const project = projects.find(p => p.id === selectedProjectId);
    const confirmed = window.confirm(`Are you sure you want to delete the project "${project?.client_name}"? This will permanently remove all associated data.`);
    if (confirmed) {
      try {
        await deleteProject(selectedProjectId);
      } catch (err) {
        alert("Failed to delete project. Please try again.");
      }
    }
  };

  return (
    <>
      <aside className="sidebar">
        {/* Logo */}
        <div className="sidebar-logo">
          <div className="sidebar-logo-mark">🧠</div>
          <h2>BA Co-Pilot</h2>
          <p>Requirement Intelligence Platform</p>
        </div>

        {/* Project Selector */}
        <div className="sidebar-project-selector">
          <span className="nav-section-label">Active Project</span>
          <div className="project-select-row">
            <select
              className="form-select project-dropdown"
              value={selectedProjectId || ''}
              onChange={(e) => selectProject(e.target.value)}
            >
              <option value="">— Select project —</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.client_name}</option>
              ))}
            </select>
            <button
              className="btn btn-primary project-new-btn"
              onClick={() => setShowModal(true)}
              title="Create New Project"
            >+</button>
            {selectedProjectId && (
              <button
                className="btn btn-danger project-delete-btn"
                onClick={handleDelete}
                title="Delete Current Project"
              >
                🗑️
              </button>
            )}
          </div>

          {/* Pipeline Progress */}
          {selectedSummary && (
            <div className="pipeline-progress">
              {PIPELINE_STEPS.map((step) => {
                const done = step.check(selectedSummary);
                return (
                  <div key={step.key} className={`pipeline-step ${done ? 'done' : ''}`}>
                    <div className="pipeline-dot">{done ? '✓' : ''}</div>
                    <span>{step.label}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="sidebar-nav">
          <span className="nav-section-label">Modules</span>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.exact}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Footer Status */}
        <div className="sidebar-footer">
          <div className="status-indicator">
            <div className={`status-dot ${online === false ? 'offline' : ''}`} />
            <span>
              {online === null
                ? 'Checking backend...'
                : online
                ? 'Backend online'
                : 'Backend offline'}
            </span>
          </div>
        </div>
      </aside>

      {showModal && (
        <CreateProjectModal
          onClose={() => setShowModal(false)}
          onCreate={createAndSelectProject}
        />
      )}
    </>
  );
}
