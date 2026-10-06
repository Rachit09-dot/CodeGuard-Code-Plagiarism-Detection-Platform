/**
 * Session API — health check and session metadata.
 */
import { get } from './client';

/** Check backend availability. Returns { status, service }. */
export function checkHealth() {
  return get('/api/health');
}

/** Deep readiness check — verifies DB connectivity. */
export function checkReady() {
  return get('/api/ready');
}
