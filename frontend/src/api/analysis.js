/**
 * Analysis API — run pairwise analysis and fetch comparison results.
 */
import { get, post } from './client';

/**
 * Run pairwise similarity analysis for a session.
 * @param {number} sessionId
 * @param {number[]} submissionIds
 * @param {number} threshold  0.0 – 1.0
 * @returns {Promise<{ session_id, total_comparisons, results, timing, ... }>}
 */
export function runAnalysis(sessionId, submissionIds, threshold) {
  return post('/api/analyze', {
    session_id: sessionId,
    submission_ids: submissionIds,
    threshold,
  });
}

/**
 * Retrieve persisted analysis results for a session.
 * @param {number} sessionId
 * @returns {Promise<{ session_id, total_comparisons, results }>}
 */
export function getResults(sessionId) {
  return get(`/api/compare?session_id=${sessionId}`);
}

/**
 * Detailed pairwise comparison with highlighted regions.
 * @param {number} sessionId
 * @param {number} leftId
 * @param {number} rightId
 * @param {number} threshold  0.0 – 1.0
 * @returns {Promise<{ file_a, file_b, score, jaccard_similarity, containment_similarity,
 *                     ast_similarity, suspicious, explanation, left_lines, right_lines,
 *                     left_matched_lines, right_matched_lines, analysis_config, ... }>}
 */
export function comparePair(sessionId, leftId, rightId, threshold) {
  return post('/api/compare', {
    session_id: sessionId,
    left_id: leftId,
    right_id: rightId,
    threshold,
  });
}
