# Project Report

## Purpose

This project implements a Python-only code plagiarism detection platform with a session-based workflow. It is designed to compare uploaded Python submissions, compute pairwise similarity, and surface suspicious matches for manual review.

## Architecture

The system uses a small full-stack arrangement:

- FastAPI backend for endpoints and validation
- SQLAlchemy models for sessions, submissions, and results
- Python plagiarism engine for normalized token comparison and fingerprint generation
- React/Vite frontend for upload and dashboard display
- SQLite database to persist historical runs without mixing current session data

## Implemented behavior

The current app features:

- upload of `.py` files only
- per-session storage and filtering
- unique pair generation only
- duplicate filename rejection within a single upload batch
- threshold validation between `0` and `1`
- suspicious vs low-similarity classification based on `score >= threshold`
- summary data returned from the backend for the dashboard

## Algorithm

The core detection logic preserves the existing Python tokenization pipeline:

- normalize identifiers, strings, and literals
- tokenize Python source code
- build overlapping k-grams with `K = 5`
- hash each k-gram
- apply MOSS-style winnowing with `W = 12`
- compute similarity between fingerprint sets
- classify pairs above the threshold as `SUSPICIOUS`

The matching view is a normalized line/region display; it does not claim AST-level matching.

## Data model

The production data model includes:

- `AnalysisSession`: stores threshold and summary metrics per analysis
- `Submission`: stores session-specific uploaded files and source content
- `AnalysisResult`: stores pairwise comparison results and session linkage

Foreign keys tie each submission and result back to the correct analysis session.

## API behavior

The app exposes the following endpoints:

- `GET /api/health`
- `POST /api/upload`
- `GET /api/submissions`
- `POST /api/analyze`
- `POST /api/compare`

The analyze endpoint filters by the current `session_id` and never mixes records from prior sessions.

## Testing

The current backend tests validate:

- one-file rejection
- two-file single comparison
- four-file six-comparison output
- duplicate filename rejection
- old-session isolation
- no self-comparison
- invalid threshold handling
- low-similarity status labeling

## Limitations

- Python-only support is implemented.
- Java/C++ uploads are intentionally rejected.
- The system is suitable for classroom or assignment screening, not a production benchmarked plagiarism platform.
- Matching is based on normalized token similarity rather than AST semantics.


Although effective, the current system has some limitations:

- supports only Python source files
- compares all pairs, which becomes O(n²) for many submissions
- cannot fully detect loop transformation or AST-level structure changes
- may produce false positives when students share common templates or training code
- is designed as a screening system, not as definitive evidence of misconduct

---

## 13. Future Scope

The system can be expanded in several directions:

1. Multi-language support using Tree-sitter
2. AST-based structural detection layer
3. Inverted index or hash lookup optimization
4. Web-based dashboard with React frontend
5. REST API with FastAPI backend
6. Database storage for submissions and results
7. Side-by-side comparison of matching regions
8. Benchmarking on labeled plagiarism datasets

These features would make the project more suitable for real-world academic and industrial deployment.

---

## 14. Security and Ethical Considerations

The system should be used responsibly. Similarity scores are warning indicators, not proof of cheating. The tool should be used only as an aid for review, and faculty or evaluators should inspect suspicious cases manually before making any conclusion.

It is also important that submitted source code is treated as untrusted input. The system should not execute user-provided code during analysis.

---

## 15. Conclusion

The Code Plagiarism Detection System demonstrates a practical and efficient way to detect suspicious code similarity using token normalization, k-gram hashing, and MOSS-style winnowing. By comparing structural code patterns instead of raw text, the system can identify copied code even when students alter variable names, comments, formatting, and some literal values.

Despite its limitations, the system is highly effective as a first-pass plagiarism detector and provides a strong foundation for future enhancements such as AST-based analysis, API integration, and a web dashboard. It is a useful project for academic assessment, coding evaluation systems, and research in source-code similarity.

---

## 16. Final Notes

This project is a useful educational implementation of plagiarism detection and can be easily extended for more advanced use cases such as multi-language comparison, automated reporting, and online submission management.

The tool is simple to run and reliable for small classroom or project evaluation environments.
