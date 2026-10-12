"""Storage, git evidence, secret scanning and reviewed writes. Stdlib only, no network."""
import difflib
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SCHEMA = "contextbridge/1"
CTX = "contextbridge"
DEFAULT_EXCLUDES = [".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
                    "id_rsa*", "id_ed25519*", "secrets.*", "credentials*.json"]


class CBError(Exception):
    def __init__(self, msg, code=2):
        super().__init__(msg)
        self.code = code


def author():
    """Who wrote a claim (set CONTEXTBRIDGE_AGENT=claude-account-a etc.); never inferred."""
    return os.environ.get("CONTEXTBRIDGE_AGENT") or "unknown"


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------- secrets
_VAL = r"(?!\[REDACTED)(?=[^\s'\"]*\d)(?=[^\s'\"]*[A-Za-z])[^\s'\"]{8,}"
PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}(?![0-9A-Za-z_-])")),
    ("stripe-key", re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("sendgrid-key", re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}")),
    ("github-fine-grained-token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("twilio-key", re.compile(r"\bSK[0-9a-f]{32}\b")),
    ("azure-key", re.compile(r"((?:AccountKey|SharedAccessKey)=)(?!\[REDACTED)([A-Za-z0-9+/=]{20,})")),
    ("url-password", re.compile(r"(\b[A-Za-z][A-Za-z0-9+.-]*://[^\s/:@]+:)(?!\[REDACTED)([^\s/@]{3,})(?=@)")),
    ("api-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("generic-secret", re.compile(
        r"(?i)((?:password|passwd|secret|token|api[_-]?key|access[_-]?key)\w*[\"']?\s*[:=]\s*[\"']?)(" + _VAL + ")")),
]


def scan(text):
    """Return [(pattern_name, line_number)] — never the secret itself."""
    return [(n, text.count("\n", 0, m.start()) + 1) for n, rx in PATTERNS for m in rx.finditer(text)]


def redact(text):
    for n, rx in PATTERNS:
        text = rx.sub(lambda m, n=n: (m.group(1) if m.lastindex else "") + f"[REDACTED:{n}]", text)
    return text


# ---------------------------------------------------------------- git
def git(root, *args):
    """stdout on success, None on failure / git missing."""
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    return r.stdout if r.returncode == 0 else None


def find_root(start=None):
    start = Path(start or os.getcwd()).resolve()
    top = git(start, "rev-parse", "--show-toplevel")
    return Path(top.strip()) if top else start


def excludes(root):
    pats = list(DEFAULT_EXCLUDES)
    f = Path(root) / ".contextbridgeignore"
    if f.exists():
        pats += [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return pats


def is_excluded(path, pats):
    base = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(base, p) for p in pats)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def nested_fingerprint(d, pats):
    """Hash a nested repo's HEAD plus the content of its own changed files, so edits and commits inside it show up."""
    head = (git(d, "rev-parse", "HEAD") or "").strip()
    h = hashlib.sha256(head.encode())
    parts = (git(d, "status", "--porcelain=v1", "-z", "-uall") or "").split("\0")
    i = 0
    while i < len(parts):
        e = parts[i]
        i += 1
        if len(e) < 4:
            continue
        if e[0] in "RC":
            i += 1
        rel = e[3:]
        if is_excluded(rel, pats):
            continue
        f = Path(d) / rel
        h.update(f"{rel}:{sha256_file(f) if f.is_file() else 'gone'}".encode())
    return "nested:" + h.hexdigest()


def snapshot(root):
    """Evidence read from the real workspace, not from anyone's memory of it."""
    root = Path(root)
    if git(root, "rev-parse", "--git-dir") is None:
        return {"git": False, "branch": None, "head": None, "dirty": [], "excluded": 0, "fingerprint": "no-git"}
    head = (git(root, "rev-parse", "HEAD") or "").strip() or None
    branch = (git(root, "branch", "--show-current") or "").strip() or "(detached)"
    pats, dirty, skipped = excludes(root), [], 0
    parts = (git(root, "status", "--porcelain=v1", "-z", "-uall") or "").split("\0")
    i = 0
    while i < len(parts):
        e = parts[i]
        i += 1
        if len(e) < 4:
            continue
        xy, p = e[:2], e[3:]
        if xy[0] in "RC":
            i += 1  # skip the rename/copy origin entry
        if p.startswith(CTX + "/"):
            continue  # our own notes must not count as drift
        if is_excluded(p, pats):
            skipped += 1
            continue
        f = root / p
        if f.is_file():
            dirty.append({"path": p, "status": "untracked" if xy == "??" else "modified", "sha256": sha256_file(f)})
        elif f.is_dir():  # nested git repo or submodule: git reports the directory, not its files
            dirty.append({"path": p, "status": "nested-repo", "sha256": nested_fingerprint(f, pats)})
        else:
            dirty.append({"path": p, "status": "deleted", "sha256": "deleted"})
    dirty.sort(key=lambda d: d["path"])
    fp = hashlib.sha256(("\n".join([head or ""] + [f"{d['path']}:{d['sha256']}" for d in dirty])).encode()).hexdigest()
    return {"git": True, "branch": branch, "head": head, "dirty": dirty, "excluded": skipped, "fingerprint": fp}


# ---------------------------------------------------------------- store
def ctx_dir(root):
    return Path(root) / CTX


def load(root, name, default):
    f = ctx_dir(root) / name
    if not f.exists():
        return default
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CBError(f"{CTX}/{name} is not valid JSON ({e}); fix or delete it")


def dump(obj):
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def new_state():
    return {"schema": SCHEMA, "objective": "", "next": None, "notes": "", "snapshot": None,
            "work": [], "evidence": [], "assumptions": []}


def next_id(items, prefix):
    n = [int(i["id"][len(prefix):]) for i in items if i["id"].startswith(prefix) and i["id"][len(prefix):].isdigit()]
    return f"{prefix}{max(n, default=0) + 1}"


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:  # LF everywhere: no CRLF diffs on Windows
        f.write(text)
    os.replace(tmp, path)


def apply(root, changes, yes=False, do_redact=False, review=True, out=print):
    """Write {relname: text} under contextbridge/ after a secret scan and a reviewable diff.

    Returns True if written (or nothing to do). Non-interactive runs without --yes are a dry run.
    """
    pending = []
    for rel, new in changes.items():
        hits = scan(new)
        if hits:
            if not do_redact:
                where = ", ".join(f"{n} (line {l})" for n, l in hits[:5])
                raise CBError(f"refusing to write {CTX}/{rel}: possible secret(s): {where}. "
                              "Remove them or re-run with --redact.")
            new = redact(new)
        f = ctx_dir(root) / rel
        old = f.read_text(encoding="utf-8") if f.exists() else ""
        if new != old:
            pending.append((f, rel, old, new))
    if not pending:
        out("No changes to persistent context.")
        return True
    if review:
        for _, rel, old, new in pending:
            out("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                             f"a/{CTX}/{rel}", f"b/{CTX}/{rel}")).rstrip())
        if not yes:
            try:  # Windows reports NUL as a tty, so also treat EOF as non-interactive
                answer = input("Apply these changes? [y/N] ") if sys.stdin.isatty() else None
            except EOFError:
                answer = None
            if answer is None:
                out("Dry run: re-run with --yes to apply the diff above.")
                raise CBError("changes not applied", code=3)
            if answer.strip().lower() != "y":
                out("Not applied.")
                return False
    for f, *_ , new in pending:
        write_atomic(f, new)
    out(f"Updated: {', '.join(r for _, r, _, _ in pending)}")
    return True
