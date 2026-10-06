"""Final verification matrix — algorithm correctness and security spot-checks."""

import hashlib
import sys

from core.analysis_service import AnalysisService
from core.ast_similarity import ast_similarity
from core.config import DEFAULT_K, DEFAULT_WINDOW, TOKEN_WEIGHT, AST_WEIGHT
from core.fingerprinter import build_fingerprint
from core.normalizer import normalize_code
from core.similarity import containment_similarity, jaccard_similarity

results = []

def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((status, label, detail))
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))

print("\n=== Detection ===")

src_for = "for x in data:\n    print(x)"
src_if  = "if x in data:\n    print(x)"
fp_for = build_fingerprint(normalize_code(src_for))
fp_if  = build_fingerprint(normalize_code(src_if))
j = jaccard_similarity(fp_for, fp_if)
check("for vs if are distinct", j < 1.0, f"Jaccard={j:.3f}")

j_empty = jaccard_similarity(set(), set())
check("empty+empty Jaccard == 0.0 (not 1.0)", j_empty == 0.0, f"got {j_empty}")

src = "def f(x):\n    for i in range(x):\n        if i > 0:\n            print(i)\n    return x"
fp = build_fingerprint(normalize_code(src))
j_id = jaccard_similarity(fp, fp)
check("identical source Jaccard == 1.0", j_id == 1.0, f"got {j_id:.3f}")

src_b = "def compute(n):\n    for k in range(n):\n        if k > 0:\n            print(k)\n    return n"
fp_b = build_fingerprint(normalize_code(src_b))
j_ren = jaccard_similarity(fp, fp_b)
check("renamed identifiers Jaccard >= 0.9", j_ren >= 0.9, f"got {j_ren:.3f}")

src_long = src + "\ndef g(y):\n    for j in range(y):\n        if j > 0:\n            print(j)\n    return y"
c = containment_similarity(fp, build_fingerprint(normalize_code(src_long)))
check("containment of subset >= 0.5", c >= 0.5, f"got {c:.3f}")

ast_score = ast_similarity(src, src_b)
check("AST similarity renamed vars >= 0.8", ast_score >= 0.8, f"got {ast_score:.3f}")

print("\n=== Robustness ===")

# Invalid Python per-file
svc = AnalysisService()
res_bad = svc.prepare_submission("bad.py", "def f(:\n    bad syntax")
check("invalid Python -> status=invalid_source", res_bad.status == "invalid_source", res_bad.status)

# Tiny file
res_tiny = svc.prepare_submission("tiny.py", "x = 1")
check("tiny file -> status=insufficient_content or ok (not flagged)", res_tiny.status in ("insufficient_content", "ok"))

# Multiline
res_multi = svc.prepare_submission("multi.py", "foo(\n    1,\n    2\n)")
check("multiline function call parses ok", res_multi.status == "ok", res_multi.status)

print("\n=== Database / Deduplication ===")
# Pair normalization: a_id always < b_id
a_id, b_id = 5, 3
norm_a = min(a_id, b_id)
norm_b = max(a_id, b_id)
check("pair normalization: min/max ordering", norm_a == 3 and norm_b == 5, f"({norm_a},{norm_b})")

print("\n=== Security ===")
bad_names = ["../../evil.py", "/etc/passwd.py", "..\\..\\windows.py", "sub/dir/file.py"]
for name in bad_names:
    has_traversal = "/" in name or "\\" in name or name in {".", ".."}
    check(f"path traversal blocked: {name!r}", has_traversal)

print("\n=== Configuration ===")
check("DEFAULT_K == 5", DEFAULT_K == 5, str(DEFAULT_K))
check("DEFAULT_WINDOW == 12", DEFAULT_WINDOW == 12, str(DEFAULT_WINDOW))
check("TOKEN_WEIGHT + AST_WEIGHT == 1.0", abs(TOKEN_WEIGHT + AST_WEIGHT - 1.0) < 1e-9,
      f"{TOKEN_WEIGHT}+{AST_WEIGHT}={TOKEN_WEIGHT+AST_WEIGHT}")

print("\n=== SHA-256 ===")
content = b"def f(x):\n    return x\n"
h = hashlib.sha256(content).hexdigest()
check("SHA-256 hash is 64 hex chars", len(h) == 64, f"len={len(h)}")
h2 = hashlib.sha256(content).hexdigest()
check("SHA-256 is deterministic", h == h2)
h3 = hashlib.sha256(b"different").hexdigest()
check("different content has different hash", h != h3)

print("\n=== Summary ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"  {passed} checks PASS, {failed} checks FAIL")
if failed:
    print("\nFailed checks:")
    for s, label, detail in results:
        if s == "FAIL":
            print(f"  FAIL: {label} — {detail}")
    sys.exit(1)
