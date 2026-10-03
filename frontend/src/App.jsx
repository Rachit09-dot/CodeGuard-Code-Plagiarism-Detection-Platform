import { useEffect, useState } from 'react';

const API_URL = 'http://127.0.0.1:8000';

function App() {
  const [files, setFiles] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [threshold, setThreshold] = useState(60);
  const [results, setResults] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [status, setStatus] = useState('Checking backend connection...');
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState({
    total_submissions: 0,
    total_comparisons: 0,
    suspicious_pair_count: 0,
    average_similarity: 0,
  });

  useEffect(() => {
    loadSubmissions();
  }, []);

  const loadSubmissions = async () => {
    try {
      const healthResp = await fetch(`${API_URL}/api/health`);
      if (!healthResp.ok) {
        throw new Error('Backend health check failed');
      }

      const healthData = await healthResp.json();
      if (healthData.status !== 'ok') {
        throw new Error('Unexpected backend response');
      }

      setFiles([]);
      setCurrentSessionId(null);
      setResults([]);
      setComparison(null);
      setSummary({ total_submissions: 0, total_comparisons: 0, suspicious_pair_count: 0, average_similarity: 0 });
      setStatus('Backend available. Ready to upload.');
    } catch (error) {
      setStatus('Backend unavailable. Please start the FastAPI server.');
    }
  };

  const handleFileChange = (event) => {
    const pickedFiles = Array.from(event.target.files || []);
    const pythonFiles = pickedFiles.filter((file) => file.name.toLowerCase().endsWith('.py'));

    if (pickedFiles.length !== pythonFiles.length) {
      setSelectedFiles([]);
      setStatus('Only Python (.py) files are supported.');
      return;
    }

    const lowerNames = pythonFiles.map((file) => file.name.toLowerCase());
    if (new Set(lowerNames).size !== lowerNames.length) {
      setSelectedFiles([]);
      setStatus('Duplicate filename found. Please upload each file once.');
      return;
    }

    setSelectedFiles(pythonFiles);
    setStatus(pythonFiles.length ? `Files selected: ${pythonFiles.length}` : 'Ready to upload');
  };

  const uploadFiles = async () => {
    if (!selectedFiles.length) {
      setStatus('Ready to upload');
      return;
    }

    const invalidFiles = selectedFiles.filter((file) => !file.name.toLowerCase().endsWith('.py'));
    if (invalidFiles.length) {
      setStatus('Only Python (.py) files are supported.');
      return;
    }

    const names = selectedFiles.map((file) => file.name.toLowerCase());
    if (new Set(names).size !== names.length) {
      setStatus('Duplicate filename found. Please upload each file once.');
      return;
    }

    const formData = new FormData();
    selectedFiles.forEach((file) => formData.append('files', file));

    try {
      setLoading(true);
      setStatus('Uploading...');

      const response = await fetch(`${API_URL}/api/upload`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Upload failed');
      }

      const sessionId = data.session_id;
      const sessionFiles = data.submissions || [];
      setCurrentSessionId(sessionId);
      setFiles(sessionFiles);
      setResults([]);
      setComparison(null);
      setSummary({
        total_submissions: sessionFiles.length,
        total_comparisons: 0,
        suspicious_pair_count: 0,
        average_similarity: 0,
      });
      setSelectedFiles([]);
      setStatus(sessionFiles.length >= 2 ? 'Uploaded. Ready to analyze.' : 'At least two submissions are required for comparison.');
    } catch (error) {
      setStatus(`Error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const analyze = async () => {
    if (!currentSessionId) {
      setStatus('Ready to upload');
      return;
    }

    if (!files.length) {
      setStatus('Upload submissions first');
      return;
    }

    if (files.length < 2) {
      setResults([]);
      setSummary({ total_submissions: files.length, total_comparisons: 0, suspicious_pair_count: 0, average_similarity: 0 });
      setStatus('At least two submissions are required for comparison.');
      return;
    }

    try {
      setLoading(true);
      setStatus('Analyzing...');

      const response = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: currentSessionId,
          submission_ids: files.map((item) => item.id),
          threshold: threshold / 100,
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Analysis failed');
      }

      setResults(data.results || []);
      setSummary({
        total_submissions: data.total_submissions || files.length,
        total_comparisons: data.total_comparisons || data.checked_pairs || 0,
        suspicious_pair_count: data.suspicious_pair_count || data.flagged_pairs || 0,
        average_similarity: data.average_similarity || 0,
      });
      setStatus(`Analysis complete. ${data.total_comparisons || data.checked_pairs || 0} comparisons, ${data.suspicious_pair_count || data.flagged_pairs || 0} suspicious pairs.`);
    } catch (error) {
      setStatus(`Error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const comparePair = async (leftId, rightId) => {
    try {
      const response = await fetch(`${API_URL}/api/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId, left_id: leftId, right_id: rightId, threshold: threshold / 100 }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Comparison failed');
      }
      setComparison(data);
      setStatus(`Compared ${data.file_a} and ${data.file_b}. ${data.explanation}`);
    } catch (error) {
      setStatus(`Comparison failed: ${error.message}`);
    }
  };

  const suspicious = results.filter((item) => item.suspicious);
  const avgScore = (summary.average_similarity || 0) * 100;
  const fileNames = selectedFiles.map((file) => file.name);

  return (
    <div className="app-shell">
      <div className="card main-card">
        <header className="page-header">
          <h1>Code Plagiarism Detection</h1>
        </header>

        <div className="upload-box">
          <label className="upload-label">Upload Python (.py) submissions</label>
          <div className="drop-zone">
            <input type="file" multiple accept=".py" onChange={handleFileChange} />
            <span>Drop .py files here</span>
          </div>
          <div className="upload-meta">
            <span>{selectedFiles.length ? fileNames.join(', ') : 'No Python files selected.'}</span>
            <button onClick={uploadFiles} disabled={loading || !selectedFiles.length}>Upload</button>
          </div>
        </div>

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

          <button className="primary" onClick={analyze} disabled={loading || files.length < 2}>Analyze</button>
        </div>

        <div className="status-box">{status}</div>
      </div>

      <div className="summary-row">
        <div className="summary-card">
          <span>Total Submissions</span>
          <strong>{summary.total_submissions || files.length}</strong>
        </div>
        <div className="summary-card">
          <span>Comparisons</span>
          <strong>{summary.total_comparisons || results.length}</strong>
        </div>
        <div className="summary-card">
          <span>Suspicious Pairs</span>
          <strong>{summary.suspicious_pair_count || suspicious.length}</strong>
        </div>
        <div className="summary-card">
          <span>Average Similarity</span>
          <strong>{avgScore.toFixed(1)}%</strong>
        </div>
      </div>

      <div className="card">
        <h2>Suspicious Submissions</h2>
        <div className="pair-list">
          {results.length ? (
            results.map((item, index) => (
              <div key={index} className={`pair-row ${item.suspicious ? 'flagged' : ''}`}>
                <button onClick={() => comparePair(files.find((f) => f.filename === item.file_a)?.id, files.find((f) => f.filename === item.file_b)?.id)}>
                  {item.file_a} ↔ {item.file_b}
                </button>
                <span>{(item.score * 100).toFixed(0)}%</span>
                <span className={item.suspicious ? 'alert high' : 'alert'}>{item.suspicious ? 'SUSPICIOUS' : 'LOW SIMILARITY'}</span>
              </div>
            ))
          ) : (
            <p>No results yet.</p>
          )}
        </div>
      </div>

      {comparison && (
        <div className="card comparison-card">
          <h3>{comparison.file_a} vs {comparison.file_b}</h3>
          <p>
            Similarity: {(comparison.score * 100).toFixed(1)}% · {comparison.status}
          </p>
          <p className="comparison-explanation">{comparison.explanation}</p>

          <div className="code-grid">
            <div className="code-panel">
              <h4>{comparison.file_a}</h4>
              {comparison.left_lines.map((line, idx) => {
                const matched = comparison.matches.some((m) => m.left === idx);
                return (
                  <pre key={`left-${idx}`} className={matched ? 'match-line' : ''}>{line || ' '}</pre>
                );
              })}
            </div>

            <div className="code-panel">
              <h4>{comparison.file_b}</h4>
              {comparison.right_lines.map((line, idx) => {
                const matched = comparison.matches.some((m) => m.right === idx);
                return (
                  <pre key={`right-${idx}`} className={matched ? 'match-line' : ''}>{line || ' '}</pre>
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
