import { useEffect, useState } from 'react';
import { checkHealth } from './api/sessions';
import { uploadFiles } from './api/submissions';
import { runAnalysis, comparePair } from './api/analysis';

function MetricBadge({ label, value, highlight }) {
  return (
    <div className={`summary-card${highlight ? ' highlight' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SimilarityBar({ score }) {
  const pct = Math.round(score * 100);
  const color = pct >= 70 ? '#e53e3e' : pct >= 40 ? '#d69e2e' : '#38a169';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      <div
        aria-hidden="true"
        style={{
          height: '8px', width: `${pct}%`, maxWidth: '120px', minWidth: '4px',
          background: color, borderRadius: '4px', transition: 'width 0.3s',
        }}
      />
      <span style={{ minWidth: '3rem', textAlign: 'right' }}>{pct}%</span>
    </div>
  );
}

export default function App() {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [sessionFiles, setSessionFiles] = useState([]);
  const [threshold, setThreshold] = useState(60);
  const [results, setResults] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [status, setStatus] = useState('Checking backend connection…');
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState({ total_submissions: 0, total_comparisons: 0, suspicious_pair_count: 0, average_similarity: 0 });

  useEffect(() => { pingBackend(); }, []);

  const pingBackend = async () => {
    try {
      const d = await checkHealth();
      if (d.status !== 'ok') throw new Error();
      setStatus('Backend available. Ready to upload.');
    } catch {
      setStatus('Backend unavailable. Please start the FastAPI server.');
    }
  };

  const handleFileChange = (e) => {
    const picked = Array.from(e.target.files || []);
    const py = picked.filter((f) => f.name.toLowerCase().endsWith('.py'));
    if (picked.length !== py.length) { setSelectedFiles([]); setStatus('Only Python (.py) files are supported.'); return; }
    const lower = py.map((f) => f.name.toLowerCase());
    if (new Set(lower).size !== lower.length) { setSelectedFiles([]); setStatus('Duplicate filename. Upload each file once.'); return; }
    setSelectedFiles(py);
    setStatus(py.length ? `${py.length} file(s) selected.` : 'Ready to upload.');
  };

  const doUpload = async () => {
    if (!selectedFiles.length) return;
    try {
      setLoading(true); setStatus('Uploading…');
      const data = await uploadFiles(selectedFiles);
      setCurrentSessionId(data.session_id);
      setSessionFiles(data.submissions || []);
      setResults([]); setComparison(null);
      setSummary({ total_submissions: data.submissions?.length ?? 0, total_comparisons: 0, suspicious_pair_count: 0, average_similarity: 0 });
      setSelectedFiles([]);
      const n = data.submissions?.length ?? 0;
      setStatus(n >= 2 ? `Uploaded ${n} file(s). Ready to analyze.` : 'Need at least 2 files to compare.');
    } catch (err) { setStatus(`Upload error: ${err.message}`); }
    finally { setLoading(false); }
  };

  const doAnalyze = async () => {
    if (!currentSessionId || sessionFiles.length < 2) { setStatus('Upload at least two Python files first.'); return; }
    try {
      setLoading(true); setStatus('Analyzing…');
      const data = await runAnalysis(currentSessionId, sessionFiles.map((f) => f.id), threshold / 100);
      setResults(data.results || []);
      const sp = data.suspicious_pair_count ?? 0, tc = data.total_comparisons ?? 0;
      setSummary({ total_submissions: data.total_submissions ?? sessionFiles.length, total_comparisons: tc, suspicious_pair_count: sp, average_similarity: data.average_similarity ?? 0 });
      setStatus(`Done. ${tc} comparison(s), ${sp} suspicious pair(s).`);
    } catch (err) { setStatus(`Analysis error: ${err.message}`); }
    finally { setLoading(false); }
  };

  const doCompare = async (leftId, rightId) => {
    if (!leftId || !rightId) return;
    try {
      setLoading(true);
      const data = await comparePair(currentSessionId, leftId, rightId, threshold / 100);
      setComparison(data); setStatus(data.explanation);
    } catch (err) { setStatus(`Comparison error: ${err.message}`); }
    finally { setLoading(false); }
  };

  const avgPct = ((summary.average_similarity || 0) * 100).toFixed(1);
  const isError = status.toLowerCase().includes('error') || status.toLowerCase().includes('unavailable');

  return (
    <div className="app-shell">
      <div className="card main-card">
        <header className="page-header">
          <h1>Code Plagiarism Detection</h1>
        </header>

        <div className="upload-box" role="region" aria-label="File upload">
          <label className="upload-label" htmlFor="file-input">
            Upload Python (.py) submissions
          </label>
          <div className="drop-zone">
            <input
              id="file-input"
              type="file"
              multiple
              accept=".py"
              aria-label="Select Python files to upload"
              onChange={handleFileChange}
            />
            <span aria-hidden="true">Drop .py files here or click to browse</span>
          </div>
          <div className="upload-meta">
            <span aria-live="polite">
              {selectedFiles.length ? selectedFiles.map((f) => f.name).join(', ') : 'No files selected.'}
            </span>
            <button onClick={doUpload} disabled={loading || !selectedFiles.length} aria-label="Upload selected files">
              {loading ? 'Working…' : 'Upload'}
            </button>
          </div>
        </div>

        <div className="controls-row" role="region" aria-label="Analysis controls">
          <div className="threshold-group">
            <label htmlFor="threshold-slider">Threshold</label>
            <input
              id="threshold-slider"
              type="range"
              min="0" max="100"
              value={threshold}
              aria-label={`Similarity threshold: ${threshold}%`}
              onChange={(e) => setThreshold(Number(e.target.value))}
            />
            <span aria-hidden="true">{threshold}%</span>
          </div>
          <button
            className="primary"
            onClick={doAnalyze}
            disabled={loading || sessionFiles.length < 2}
            aria-label="Run plagiarism analysis"
          >
            {loading ? 'Analyzing…' : 'Analyze'}
          </button>
        </div>

        <div
          className={`status-box${isError ? ' error' : ''}`}
          role="status"
          aria-live="polite"
        >
          {status}
        </div>
      </div>

      <div className="summary-row" role="region" aria-label="Analysis summary">
        <MetricBadge label="Total Submissions" value={summary.total_submissions || sessionFiles.length} />
        <MetricBadge label="Comparisons" value={summary.total_comparisons || results.length} />
        <MetricBadge label="Suspicious Pairs" value={summary.suspicious_pair_count} highlight={summary.suspicious_pair_count > 0} />
        <MetricBadge label="Avg Similarity" value={`${avgPct}%`} />
      </div>

      <div className="card" role="region" aria-label="Comparison results">
        <h2>Comparison Results</h2>
        {results.length === 0 ? (
          <p className="empty-state">
            {sessionFiles.length >= 2 ? 'Press Analyze to run pairwise comparison.' : 'Upload at least two Python files to get started.'}
          </p>
        ) : (
          <div className="pair-list" role="list">
            {results.map((item, idx) => {
              const lf = sessionFiles.find((f) => f.filename === item.file_a);
              const rf = sessionFiles.find((f) => f.filename === item.file_b);
              const label = `${item.file_a} compared to ${item.file_b}, similarity ${Math.round(item.score * 100)}%, ${item.suspicious ? 'suspicious' : 'OK'}`;
              return (
                <div key={idx} className={`pair-row${item.suspicious ? ' flagged' : ''}`} role="listitem">
                  <button
                    onClick={() => doCompare(lf?.id, rf?.id)}
                    disabled={!lf || !rf}
                    aria-label={label}
                    title="Click to view highlighted diff"
                  >
                    {item.file_a} ↔ {item.file_b}
                  </button>
                  <SimilarityBar score={item.score} />
                  {item.is_exact_duplicate && <span className="alert high" aria-label="Exact content duplicate">EXACT COPY</span>}
                  <span className={item.suspicious ? 'alert high' : 'alert low'} aria-label={item.suspicious ? 'Suspicious' : 'OK'}>
                    {item.suspicious ? 'SUSPICIOUS' : 'OK'}
                  </span>
                  {item.containment_similarity !== undefined && (
                    <span className="metric-pill" title="Containment similarity">Contain: {(item.containment_similarity * 100).toFixed(0)}%</span>
                  )}
                  {item.ast_similarity !== undefined && (
                    <span className="metric-pill" title="AST structural similarity">AST: {(item.ast_similarity * 100).toFixed(0)}%</span>
                  )}
                  {item.status_a && item.status_a !== 'ok' && <span className="metric-pill warn">A: {item.status_a}</span>}
                  {item.status_b && item.status_b !== 'ok' && <span className="metric-pill warn">B: {item.status_b}</span>}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {comparison && (
        <div className="card comparison-card" role="region" aria-label={`Comparison: ${comparison.file_a} vs ${comparison.file_b}`}>
          <h3>{comparison.file_a} <span style={{ fontWeight: 400 }}>vs</span> {comparison.file_b}</h3>
          <div className="comparison-metrics" aria-label="Similarity metrics">
            <span>Combined: {(comparison.score * 100).toFixed(1)}%</span>
            {comparison.jaccard_similarity !== undefined && <span>Token (Jaccard): {(comparison.jaccard_similarity * 100).toFixed(1)}%</span>}
            {comparison.containment_similarity !== undefined && <span>Containment: {(comparison.containment_similarity * 100).toFixed(1)}%</span>}
            {comparison.ast_similarity !== undefined && <span>AST: {(comparison.ast_similarity * 100).toFixed(1)}%</span>}
            <span className={comparison.suspicious ? 'alert high' : 'alert low'}>
              {comparison.is_exact_duplicate ? 'EXACT COPY' : comparison.status}
            </span>
          </div>
          {comparison.analysis_config && (
            <div className="comparison-metrics" style={{ fontSize: '0.78rem', opacity: 0.7 }} aria-label="Analysis configuration">
              <span>k={comparison.analysis_config.k_gram_size}</span>
              <span>window={comparison.analysis_config.window_size}</span>
              <span>threshold={Math.round(comparison.analysis_config.threshold * 100)}%</span>
              <span>token_w={comparison.analysis_config.token_weight}</span>
              <span>ast_w={comparison.analysis_config.ast_weight}</span>
            </div>
          )}
          <p className="comparison-explanation">{comparison.explanation}</p>
          <div className="code-grid">
            <div className="code-panel">
              <h4>{comparison.file_a}</h4>
              {comparison.left_lines.map((line, idx) => {
                const matched = comparison.left_matched_lines
                  ? comparison.left_matched_lines.includes(idx)
                  : comparison.matches?.some((m) => m.left === idx);
                return (
                  <pre key={`l-${idx}`} className={matched ? 'match-line' : ''} aria-label={matched ? `Line ${idx + 1} (matching)` : undefined}>
                    <span className="line-num" aria-hidden="true">{idx + 1}</span>{line || ' '}
                  </pre>
                );
              })}
            </div>
            <div className="code-panel">
              <h4>{comparison.file_b}</h4>
              {comparison.right_lines.map((line, idx) => {
                const matched = comparison.right_matched_lines
                  ? comparison.right_matched_lines.includes(idx)
                  : comparison.matches?.some((m) => m.right === idx);
                return (
                  <pre key={`r-${idx}`} className={matched ? 'match-line' : ''} aria-label={matched ? `Line ${idx + 1} (matching)` : undefined}>
                    <span className="line-num" aria-hidden="true">{idx + 1}</span>{line || ' '}
                  </pre>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
