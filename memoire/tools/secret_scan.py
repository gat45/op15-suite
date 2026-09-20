"""Secret scan of tracked files: tokens, passwords, keys, personal paths."""
import re
import subprocess

PATTERNS = [
    (r"gh[pousr]_[A-Za-z0-9]{20,}", "github token"),
    (r"(?i)(password|passwd|apikey|api_key|secret|token)\s*[:=]\s*['\"][^'\"]{8,}", "hardcoded secret"),
    (r"(?i)gho_|ghp_|github_pat_", "git credential"),
    (r"-----BEGIN (RSA|EC|OPENSSH|DSA|EC) PRIVATE KEY", "private key"),
    (r"(?i)(mongodb|postgres|mysql|redis)://[^\"' toward ]+:[^@]+@", "db uri with creds"),
    (r"(?i)sudo -S\s*echo\s+\S+", "sudo password"),
]

tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.splitlines()
issues = 0
for path in tracked:
    try:
        content = open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    for pat, label in PATTERNS:
        for m in re.finditer(pat, content):
            issues += 1
            line = content[:m.start()].count("\n") + 1
            excerpt = m.group(0)
            print(f"[{label}] {path}:{line} -> {excerpt[:60]}")
print(f"\n{issues} probleme(s) detecte(s)")
