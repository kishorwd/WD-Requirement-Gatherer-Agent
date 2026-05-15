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
  api.post('/api/v1/projects/create', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);

export const deleteProject = (projectId) =>
  api.delete(`/api/v1/projects/${projectId}`).then(r => r.data);

// =====================
// Pre-Meeting Intelligence
// =====================
export const generateBrief = (formData, signal) =>
  api.post('/api/v1/generate-brief', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    signal,
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

/**
 * Streaming transcript analysis via fetch() + ReadableStream.
 * (EventSource doesn't support POST/file uploads, so we use fetch.)
 *
 * @param {FormData} formData  - same shape as analyzeTranscript
 * @param {Function} onEvent   - called with each progress event {status, message, step}
 * @param {Function} onComplete - called with the final {status:'complete', session_id, analysis_result, ...}
 * @param {Function} onError   - called with an error string
 * @returns {Function} cleanup — call to abort the stream
 */
export const analyzeTranscriptStream = (formData, onEvent, onComplete, onError) => {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(`${BASE_URL}/api/v1/meetings/analyze-transcript-stream`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });

      if (!response.ok) {
        let msg = `HTTP ${response.status}`;
        try { const body = await response.json(); msg = body.detail || msg; } catch {}
        onError(msg);
        return;
      }

      const reader  = response.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';          // keep partial line for next chunk

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(trimmed.slice(6));
            if (data.status === 'complete') {
              onComplete(data);
            } else if (data.status === 'error') {
              onError(data.message || 'Analysis failed');
              return;
            } else {
              onEvent(data);
            }
          } catch (e) {
            console.error('[SSE parse error]', e, '| line:', trimmed);
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        onError(err.message || 'Stream connection failed');
      }
    }
  })();

  return () => controller.abort();
};

export const getProjectSessions = (projectId) =>
  api.get('/api/v1/meetings/sessions', { params: { project_id: projectId } }).then(r => r.data);

export const getSessionRequirements = (sessionId) =>
  api.get(`/api/v1/meetings/session/${sessionId}/requirements`).then(r => r.data);

// =====================
// Scope Gap Analysis
// =====================
export const analyzeScope = (projectId, signal) =>
  api.post(`/api/v1/scopes/projects/${projectId}/analyze-scope`, null, { signal }).then(r => r.data);

export const getProjectRequirements = (projectId, filters = {}) =>
  api.get(`/api/v1/scopes/projects/${projectId}/requirements`, { params: filters }).then(r => r.data);

// =====================
// User Story Generator
// =====================
export const getStoryProjects = () =>
  api.get('/api/v1/stories/projects').then(r => r.data);

export const generateStories = (projectId, signal) =>
  api.post(`/api/v1/stories/generate-stories/${projectId}`, null, {
    timeout: 0,  // No timeout — multi-agent loop can take 15-30 min for large projects
    signal,
  }).then(r => r.data);

export const generateStoriesStream = (projectId, onUpdate, onComplete, onError) => {
  const url = `${BASE_URL}/api/v1/stories/generate-stories-stream/${projectId}`;
  const eventSource = new EventSource(url);

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.status === 'complete') {
        eventSource.close();
        onComplete(data.stories);
      } else if (data.status === 'error') {
        eventSource.close();
        onError(data.message);
      } else {
        onUpdate(data);
      }
    } catch (err) {
      console.error('Error parsing SSE data:', err);
    }
  };

  eventSource.onerror = (err) => {
    console.error('EventSource error:', err);
    eventSource.close();
    onError('Connection to server lost. Please try again.');
  };

  return () => eventSource.close(); // Return cleanup function
};

export const getExistingStories = (projectId) =>
  api.get(`/api/v1/stories/project/${projectId}`).then(r => r.data);

export const getClarifications = (projectId) =>
  api.get(`/api/v1/stories/project/${projectId}/clarifications`).then(r => r.data);

export const submitClarificationAnswers = (projectId, answers, signal) =>
  api.post(`/api/v1/stories/project/${projectId}/clarifications/answer`, { answers }, {
    timeout: 0,  // regeneration can take several minutes
    signal,
  }).then(r => r.data);

// =====================
// Health check
// =====================
export const checkHealth = () =>
  api.get('/').then(() => true).catch(() => false);

export default api;

