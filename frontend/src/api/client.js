/**
 * Base API client.
 *
 * Centralises:
 *   - base URL (from VITE_API_URL env var, falls back to localhost)
 *   - JSON serialisation / deserialisation
 *   - error parsing (detail string + optional error_code)
 *   - request timeout (10 s default)
 *
 * Usage:
 *   import { get, post, postForm } from './api/client';
 *   const data = await get('/api/health');
 *   const result = await post('/api/analyze', { session_id, threshold });
 */

export const BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const DEFAULT_TIMEOUT_MS = 10_000;

/**
 * Parse an API error response into a human-readable string.
 * Handles both plain strings and our structured { detail, error_code } shape.
 */
export function parseApiError(data, fallback = 'Request failed') {
  if (!data) return fallback;
  if (typeof data.detail === 'string') return data.detail;
  if (typeof data.detail === 'object' && data.detail?.detail) return data.detail.detail;
  if (typeof data === 'string') return data;
  return fallback;
}

/**
 * Core fetch wrapper with timeout support.
 * Throws an Error with a user-friendly message on non-2xx responses.
 */
async function request(path, options = {}) {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...fetchOptions,
      signal: controller.signal,
    });
  } catch (err) {
    if (err.name === 'AbortError') throw new Error('Request timed out. Please try again.');
    throw new Error('Network error. Is the backend running?');
  } finally {
    clearTimeout(timer);
  }

  // Try to parse JSON body regardless of status
  let data;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const msg = parseApiError(data, `Server error (${response.status})`);
    const err = new Error(msg);
    err.status = response.status;
    err.errorCode = data?.error_code ?? null;
    err.data = data;
    throw err;
  }

  return data;
}

/** GET request. */
export function get(path, options = {}) {
  return request(path, { method: 'GET', ...options });
}

/** POST request with JSON body. */
export function post(path, body, options = {}) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    ...options,
  });
}

/** POST request with FormData (file uploads). */
export function postForm(path, formData, options = {}) {
  return request(path, {
    method: 'POST',
    body: formData,
    // Do NOT set Content-Type — browser sets it with boundary automatically
    ...options,
  });
}
