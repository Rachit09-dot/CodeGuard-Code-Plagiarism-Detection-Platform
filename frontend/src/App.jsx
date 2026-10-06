import { useEffect, useState } from 'react';

// Use the Vite environment variable; fall back to localhost for development.
const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

// ---- Small helper components -----------------------------------------------

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
        style={{
          height: '8px',
          width: `${pct}%`,
          maxWidth: '120px',
          minWidth: '4px',
          background: color,
          borderRadius: '4px',
          transition: 'width 0.3s',
        }}
      />
      <span style={{ minWidth: '3rem', textAlign: 'right' }}>{pct}%</span>
    </div>
  );
}

// ---- Main App ---------------------------------------------------------------

function App() {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [sessionFiles, setSessionFiles] = useState([]);
  const [threshold, setThreshold] = useState(60);
  const [results, setResults] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [status, setStatus] = useState('Checking backend connection…');
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState({
    total_submissions: 0,
    total_comparisons: 0,
    suspicious_pair_count: 0,
    average_similarity: 0,
  });

  useEffect(() => {
    checkBackend();
  }, []);

  const checkBackend = async () => {
    try {
      const resp = await fetch(`${API_URL}/api/health`);
      if (!resp.ok) throw new Error('Health check failed');
      const data = await resp.json();
      if (data.status !== 'ok') throw new Error('Unexpected backend response');
      setStatus('Backend available. Ready to upload.');
    } catch {
      setStatus('Backend unavailable. Please start the FastAPI server.');
    }
  };

  const handleFileChange = (e) => {
    const picked = Array.from(e.target.files || []);
    const pyFiles = picked.filter((f) => f.name.toLowerCase().endsWith('.py'));

    if (picked.length !== pyFiles.length) {
      setSelectedFiles([]);
      setStatus('Only Python (.py) files are supported.');
      return;
    }
    const lower = pyFiles.map((f) => f.name.toLowerCase());
    if (new Set(lower).size !== lower.length) {
      setSelectedFiles([]);
      setStatus('Duplicate filename found. Upload each file once.');
      return;
    }
    setSelectedFiles(pyFiles);
    setStatus(pyFiles.length ? `${pyFiles.length} file(s) selected.` : 'Ready to upload.');
  };

  const uploadFiles = async () => {
    if (!selectedFiles.length) return;

    const formData = new FormData();
    selectedFiles.forEach((f) => formData.append('files', f));

    try {
      setLoading(true);
      setStatus('Uploading…');
      const resp = await fetch(`${API_URL}/api/upload`, { method: 'POST', body: formData });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Upload failed');

      setCurrentSessionId(data.session_id);
      setSessionFiles(data.submissions || []);
      setResults([]);
      setComparison(null);
      setSummary({
        total_submissions: data.submissions?.length ?? 0,
        total_comparisons: 0,
        suspicious_pair_count: 0,
        average_similarity: 0,
      });
      setSelectedFiles([]);
      const n = data.submissions?.length ?? 0;
      setStatus(
        n >= 2
          ? `Uploaded ${n} file(s). Ready to analyze.`
          : 'Uploaded. At least two submissions are required for comparison.',
      );
    } catch (err) {
      setStatus(`Upload error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const analyze = async () => {
    if (!currentSessionId || sessionFiles.length < 2) {
      setStatus('Upload at least two Python files first.');
      return;
    }

    try {
      setLoading(true);
      setStatus('Analyzing…');
      const resp = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: currentSessionId,
          submission_ids: sessionFiles.map((f) => f.id),
          threshold: threshold / 100,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Analysis failed');

      setResults(data.results || []);
      const sp = data.suspicious_pair_count ?? data.flagged_pairs ?? 0;
      const tc = data.total_comparisons ?? data.checked_pairs ?? 0;
      setSummary({
        total_submissions: data.total_submissions ?? sessionFiles.length,
        total_comparisons: tc,
        suspicious_pair_count: sp,
        average_similarity: data.average_similarity ?? 0,
      });
      setStatus(`Done. ${tc} comparison(s), ${sp} suspicious pair(s).`);
    } catch (err) {
      setStatus(`Analysis error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const comparePair = async (leftId, rightId) => {
    if (!leftId || !rightId) return;
    try {
      setLoading(true);
      const resp = await fetch(`${API_URL}/api/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: currentSessionId,
          left_id: leftId,
          right_id: rightId,
          threshold: threshold / 100,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Comparison failed');
      setComparison(data);
      setStatus(data.explanation);
    } catch (err) {
      setStatus(`Comparison error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const avgPct = ((summary.average_similarity || 0) * 100).toFixed(1);

  return (
    <div className="app-shell">
      {/* ── Header card ────────────────────────────────────────── */}
      <div className="card main-card">
        <header className="page-header">
          <h1>Code Plagiarism Detection</h1>
        </header>

        {/* Upload */}
        <div className="upload-box">
          <label className="upload-label">Upload Python (.py) submissions</label>
          <div className="drop-zone">
            <input type="file" multiple accept=".py" onChange={handleFileChange} />
            <span>Drop .py files here or click to browse</span>
          </div>
          <div className="upload-meta">
            <span>
              {selectedFiles.length
                ? selectedFiles.map((f) => f.name).join(', ')
                : 'No files selected.'}
            </span>
            <button onClick={uploadFiles} disabled={loading || !selectedFiles.length}>
              {loading ? 'Working…' : 'Upload'}
            </button>
          </div>
        </div>

        {/* Threshold + Analyze */}
        <div className="controls-row">
          <div className="threshold-group">
            <label>Threshold</label>
            <input
              type="range"
              min="0"
              max="100"
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
            />
            <span>{threshold}%</span>
          </div>
          <button
            className="primary"
            onClick={analyze}
            disabled={loading || sessionFiles.length < 2}
          >
            {loading ? 'Analyzing…' : 'Analyze'}
          </button>
        </div>

        <div className={`status-box${status.toLowerCase().includes('error') ? ' error' : ''}`}>
          {status}
        </div>
      </div>

      {/* ── Summary row ─────────────────────────────────────────── */}
      <div className="summary-row">
        <MetricBadge label="Total Submissions" value={summary.total_submissions || sessionFiles.length} />
        <MetricBadge label="Comparisons" value={summary.total_comparisons || results.length} />
        <MetricBadge
          label="Suspicious Pairs"
          value={summary.suspicious_pair_count}
          highlight={summary.suspicious_pair_count > 0}
        />
        <MetricBadge label="Avg Similarity" value={`${avgPct}%`} />
      </div>

      {/* ── Results list ────────────────────────────────────────── */}
      <div className="card">
        <h2>Comparison Results</h2>
        {results.length === 0 ? (
          <p className="empty-state">
            {sessionFiles.length >= 2
              ? 'Press Analyze to run pairwise comparison.'
              : 'Upload at least two Python files to get started.'}
          </p>
        ) : (
          <div className="pair-list">
            {results.map((item, idx) => {
              const leftFile = sessionFiles.find((f) => f.filename === item.file_a);
              const rightFile = sessionFiles.find((f) => f.filename === item.file_b);
              return (
                <div key={idx} className={`pair-row${item.suspicious ? ' flagged' : ''}`}>
                  <button
                    onClick={() => comparePair(leftFile?.id, rightFile?.id)}
                    disabled={!leftFile || !rightFile}
                    title="Click to view highlighted diff"
                  >
                    {item.file_a} ↔ {item.file_b}
                  </button>
                  <SimilarityBar score={item.score} />
                  {item.is_exact_duplicate && (
                    <span className="alert high" title="Exact content duplicate (SHA-256 match)">
                      EXACT COPY
                    </span>
                  )}
                  <span className={item.suspicious ? 'alert high' : 'alert low'}>
                    {item.suspicious ? 'SUSPICIOUS' : 'OK'}
                  </span>
                  {/* Extra metric pills */}
                  {item.containment_similarity !== undefined && (
                    <span className="metric-pill" title="Containment similarity">
                      Contain: {(item.containment_similarity * 100).toFixed(0)}%
                    </span>
                  )}
                  {item.ast_similarity !== undefined && (
                    <span className="metric-pill" title="AST structural similarity">
                      AST: {(item.ast_similarity * 100).toFixed(0)}%
                    </span>
                  )}
                  {(item.status_a && item.status_a !== 'ok') && (
                    <span className="metric-pill warn" title={`File A status: ${item.status_a}`}>
                      A: {item.status_a}
                    </span>
                  )}
                  {(item.status_b && item.status_b !== 'ok') && (
                    <span className="metric-pill warn" title={`File B status: ${item.status_b}`}>
                      B: {item.status_b}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Detailed comparison / highlighting ──────────────────── */}
      {comparison && (
        <div className="card comparison-card">
          <h3>
            {comparison.file_a} <span style={{ fontWeight: 400 }}>vs</span> {comparison.file_b}
          </h3>

          {/* Metrics summary */}
          <div className="comparison-metrics">
            <span>Combined: {(comparison.score * 100).toFixed(1)}%</span>
            {comparison.jaccard_similarity !== undefined && (
              <span>Token (Jaccard): {(comparison.jaccard_similarity * 100).toFixed(1)}%</span>
            )}
            {comparison.containment_similarity !== undefined && (
              <span>Containment: {(comparison.containment_similarity * 100).toFixed(1)}%</span>
            )}
            {comparison.ast_similarity !== undefined && (
              <span>AST: {(comparison.ast_similarity * 100).toFixed(1)}%</span>
            )}
            <span className={comparison.suspicious ? 'alert high' : 'alert low'}>
              {comparison.is_exact_duplicate ? 'EXACT COPY' : comparison.status}
            </span>
          </div>

          <p className="comparison-explanation">{comparison.explanation}</p>

          {/* Side-by-side code panels */}
          <div className="code-grid">
            <div className="code-panel">
              <h4>{comparison.file_a}</h4>
              {comparison.left_lines.map((line, idx) => {
                const matched = comparison.left_matched_lines
                  ? comparison.left_matched_lines.includes(idx)
                  : comparison.matches?.some((m) => m.left === idx);
                return (
                  <pre key={`left-${idx}`} className={matched ? 'match-line' : ''}>
                    <span className="line-num">{idx + 1}</span>
                    {line || ' '}
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
                  <pre key={`right-${idx}`} className={matched ? 'match-line' : ''}>
                    <span className="line-num">{idx + 1}</span>
                    {line || ' '}
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

export default App;
