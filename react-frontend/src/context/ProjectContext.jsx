import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getProjects, getProjectDetail, createProject as apiCreateProject, deleteProject as apiDeleteProject } from '../api/client';

const ProjectContext = createContext(null);

export function ProjectProvider({ children }) {
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(() => {
    // Restore from localStorage
    const saved = localStorage.getItem('selectedProjectId');
    return saved ? Number(saved) : null;
  });
  const [projectDetail, setProjectDetail] = useState(null);
  const [loading, setLoading] = useState(false);

  // Fetch project list
  const refreshProjects = useCallback(async () => {
    try {
      const data = await getProjects();
      setProjects(data);
      return data;
    } catch {
      return [];
    }
  }, []);

  // Load project list on mount
  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  // Fetch full detail when selectedProjectId changes
  const selectProject = useCallback(async (id) => {
    const numId = id ? Number(id) : null;
    setSelectedProjectId(numId);
    if (numId) {
      localStorage.setItem('selectedProjectId', String(numId));
    } else {
      localStorage.removeItem('selectedProjectId');
    }

    if (!numId) {
      setProjectDetail(null);
      return null;
    }

    setLoading(true);
    try {
      const detail = await getProjectDetail(numId);
      setProjectDetail(detail);
      return detail;
    } catch {
      setProjectDetail(null);
      setSelectedProjectId(null);
      localStorage.removeItem('selectedProjectId');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // Refresh detail for the currently selected project
  const refreshProjectDetail = useCallback(async () => {
    if (!selectedProjectId) return null;
    try {
      const detail = await getProjectDetail(selectedProjectId);
      setProjectDetail(detail);
      // Also refresh the list to update summary counts
      refreshProjects();
      return detail;
    } catch {
      return projectDetail;
    }
  }, [selectedProjectId, projectDetail, refreshProjects]);

  // Auto-load detail on mount if we had a saved selection
  useEffect(() => {
    if (selectedProjectId && !projectDetail) {
      selectProject(selectedProjectId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Create a project and select it
  const createAndSelectProject = useCallback(async (clientName, industry) => {
    const fd = new FormData();
    fd.append('client_name', clientName);
    fd.append('industry', industry);
    const newProject = await apiCreateProject(fd);
    await refreshProjects();
    await selectProject(newProject.id);
    return newProject;
  }, [refreshProjects, selectProject]);

  // Delete a project
  const deleteProject = useCallback(async (id) => {
    try {
      await apiDeleteProject(id);
      if (selectedProjectId === id) {
        setSelectedProjectId(null);
        setProjectDetail(null);
        localStorage.removeItem('selectedProjectId');
      }
      await refreshProjects();
    } catch (err) {
      console.error("Failed to delete project:", err);
      throw err;
    }
  }, [selectedProjectId, refreshProjects]);

  const value = {
    projects,
    selectedProjectId,
    projectDetail,
    loading,
    selectProject,
    refreshProjects,
    refreshProjectDetail,
    createAndSelectProject,
    deleteProject,
  };

  return (
    <ProjectContext.Provider value={value}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error('useProject must be used within a ProjectProvider');
  return ctx;
}
