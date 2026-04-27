import axios from 'axios';

const BASE_URL = 'http://127.0.0.1:8000';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 600000, // 10 min for long AI operations
});

// =====================
// Projects
// =====================
export const getProjects = () => api.get('/api/v1/projects').then(r => r.data);

export const getProjectDetail = (projectId) =>
  api.get(`/api/v1/projects/${projectId}`).then(r => r.data);

export const createProject = (formData) =>
  api.post('/api/v1/projects/create', formData).then(r => r.data);

export const deleteProject = (projectId) =>
  api.delete(`/api/v1/projects/${projectId}`).then(r => r.data);

// =====================
// Pre-Meeting Intelligence
// =====================
export const generateBrief = (formData) =>
  api.post('/api/v1/generate-brief', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);

// =====================
// Post-Meeting Analysis
// =====================
export const uploadDiscoveryPlan = (projectId, formData) =>
  api.post(`/api/v1/meetings/project/${projectId}/upload-plan`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);

export const extractSpeakers = (formData) =>
  api.post('/api/v1/meetings/extract-speakers', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);

export const analyzeTranscript = (formData) =>
  api.post('/api/v1/meetings/analyze-transcript', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);

export const getProjectSessions = (projectId) =>
  api.get('/api/v1/meetings/sessions', { params: { project_id: projectId } }).then(r => r.data);

export const getSessionRequirements = (sessionId) =>
  api.get(`/api/v1/meetings/session/${sessionId}/requirements`).then(r => r.data);

// =====================
// Scope Gap Analysis
// =====================
export const analyzeScope = (projectId) =>
  api.post(`/api/v1/scopes/projects/${projectId}/analyze-scope`).then(r => r.data);

export const getProjectRequirements = (projectId, filters = {}) =>
  api.get(`/api/v1/scopes/projects/${projectId}/requirements`, { params: filters }).then(r => r.data);

// =====================
// User Story Generator
// =====================
export const getStoryProjects = () =>
  api.get('/api/v1/stories/projects').then(r => r.data);

export const generateStories = (projectId) =>
  api.post(`/api/v1/stories/generate-stories/${projectId}`).then(r => r.data);

// =====================
// Health check
// =====================
export const checkHealth = () =>
  api.get('/').then(() => true).catch(() => false);

export default api;

