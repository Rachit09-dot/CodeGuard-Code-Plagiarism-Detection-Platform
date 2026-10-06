/**
 * Submissions API — upload and list.
 */
import { get, postForm } from './client';

/**
 * Upload Python files and create a new session.
 * @param {File[]} files
 * @returns {Promise<{ session_id, total_submissions, submissions }>}
 */
export function uploadFiles(files) {
  const form = new FormData();
  files.forEach((f) => form.append('files', f));
  return postForm('/api/upload', form);
}

/**
 * List all submissions for a session.
 * @param {number} sessionId
 * @returns {Promise<{ session_id, total_submissions, submissions }>}
 */
export function listSubmissions(sessionId) {
  return get(`/api/submissions?session_id=${sessionId}`);
}
