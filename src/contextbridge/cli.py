"""contextbridge CLI. Exit codes: 0 ok, 1 drift/overlap found, 2 error or secret, 3 diff not applied."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .core import (CBError, CTX, SCHEMA, apply, author, dump, find_root, load, new_state, next_id, now,
                   redact, scan, snapshot)
from .features import (EXIT, GATE_ADVICE, RESUME_RULES, add_decision, check_graph, drift, fmt_drift, fmt_node, gate,
                       new_graph, query, render_decisions, render_handoff, session_report, trace)

STATUSES = ("completed", "attempted", "planned")


def _parent():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--root", help="repository root (default: auto-detect)")
    p.add_argument("-y", "--yes", action="store_true", help="apply the reviewed diff without prompting")
    p.add_argument("--redact", action="store_true", help="redact detected secrets instead of refusing")
    return p


def build():
    par = _parent()
    ap = argparse.ArgumentParser(prog="contextbridge", description="Verified, portable, private project memory for AI coding sessions.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, help, **kw):
        return sub.add_parser(name, help=help, parents=[par], **kw)

    c = add("init", "create contextbridge/ and privacy defaults")
    c.add_argument("--local-only", action="store_true", help="add contextbridge/ to .git/info/exclude")
    for name, hlp in (("checkpoint", "snapshot real repo state into state.json + HANDOFF.md"),
                      ("save", "validate (graph, sessions) then checkpoint, with secret scan + diff review")):
        c = add(name, hlp)
        c.add_argument("--objective")
        c.add_argument("--next", dest="next_text")
        c.add_argument("--next-path", action="append", default=[])
        c.add_argument("--note")
    w = add("work", "track completed / attempted / planned work").add_subparsers(dest="sub", required=True)
    x = w.add_parser("add", parents=[par])
    x.add_argument("text")
    x.add_argument("--status", choices=STATUSES, default="planned")
    x.add_argument("--path", action="append", default=[])
    x.add_argument("--evidence", action="append", default=[], help="passing run id (E1) that backs this item")
    x = w.add_parser("set", parents=[par])
    x.add_argument("id")
    x.add_argument("status", choices=STATUSES)
    x.add_argument("--evidence", action="append", default=[])
    c = add("run", "run a command and record the real result as evidence")
    c.add_argument("--timeout", type=int, default=600)
    c.add_argument("argv", nargs=argparse.REMAINDER, help="-- command ...")
    c = add("assume", "record a checkable assumption")
    c.add_argument("text")
    c.add_argument("--file")
    c.add_argument("--contains")
    d = add("decision", "decision graph").add_subparsers(dest="sub", required=True)
    x = d.add_parser("add", parents=[par])
    x.add_argument("title")
    x.add_argument("--why", required=True)
    for f in ("rejected", "requirement", "code", "test", "depends", "consequence"):
        x.add_argument(f"--{f}", action="append", default=[])
    g = add("graph", "query the decision graph").add_subparsers(dest="sub", required=True)
    for n in ("show", "check", "render"):
        g.add_parser(n, parents=[par])
    for n in ("query", "trace"):
        g.add_parser(n, parents=[par]).add_argument("arg")
    c = add("drift", "compare the checkpoint with the actual repository")
    c.add_argument("--json", action="store_true")
    add("status", "verified state vs claims, plus drift")
    c = add("resume", "resume safety gate + agent-neutral resume prompt (exit 0 READY, 1 REVIEW_REQUIRED, 2 BLOCKED)")
    c.add_argument("--check", action="store_true", help="print only the gate verdict")
    c.add_argument("--json", action="store_true")
    s = add("session", "multi-session coordination").add_subparsers(dest="sub", required=True)
    x = s.add_parser("start", parents=[par])
    x.add_argument("name")
    x.add_argument("--task", default="")
    x.add_argument("--agent", default="unknown")
    x.add_argument("--claim", action="append", default=[])
    x.add_argument("--depends", action="append", default=[])
    s.add_parser("finish", parents=[par]).add_argument("name")
    s.add_parser("list", parents=[par])
    c = add("export", "write a portable single-file bundle")
    c.add_argument("-o", "--output", required=True)
    c = add("import", "import a bundle (reviewed diff)")
    c.add_argument("bundle")
    c = add("scan", "secret-scan files (exit 2 if any found)")
    c.add_argument("paths", nargs="+")
    return ap


# ---------------------------------------------------------------- helpers
class Ctx:
    def __init__(self, a):
        self.a = a
        self.root = find_root(a.root)
        self.err = None
        try:
            self.state = load(self.root, "state.json", None)
            self.graph = load(self.root, "graph.json", None)
            self.sessions = load(self.root, "sessions.json", None)
        except CBError as e:
            if a.cmd != "resume":
                raise
            self.err, self.state, self.graph, self.sessions = str(e), None, None, None

    def need(self):
        if self.state is None:
            self.state, self.graph, self.sessions = new_state(), new_graph(), {"schema": SCHEMA, "sessions": []}
        self.graph = self.graph or new_graph()
        self.sessions = self.sessions or {"schema": SCHEMA, "sessions": []}
        return self

    def save(self, extra=None, **kw):
        ch = {"state.json": dump(self.state), "graph.json": dump(self.graph), "sessions.json": dump(self.sessions),
              "HANDOFF.md": render_handoff(self.state, self.graph)}
        ch.update(extra or {})
        return apply(self.root, ch, self.a.yes, self.a.redact, **kw)


def _sorted_status(state):
    return {s: [w for w in state["work"] if w["status"] == s] for s in STATUSES}


# ---------------------------------------------------------------- commands
def cmd_init(c):
    c.need()
    ch = {}
    if not (c.root / ".contextbridgeignore").exists():
        (c.root / ".contextbridgeignore").write_text(
            "# Files matching these patterns are never recorded by ContextBridge (defaults: .env*, *.pem, *.key, ...)\n",
            encoding="utf-8")
    if c.a.local_only:
        ex = c.root / ".git" / "info" / "exclude"
        if ex.parent.is_dir():
            cur = ex.read_text(encoding="utf-8") if ex.exists() else ""
            if f"{CTX}/" not in cur.splitlines():
                with open(ex, "w", encoding="utf-8", newline="\n") as f:
                    f.write(cur + ("" if cur.endswith("\n") or not cur else "\n") + f"{CTX}/\n")
                print(f"Added {CTX}/ to .git/info/exclude (local-only).")
        else:
            print("Not a git repo: nothing to exclude.", file=sys.stderr)
    return 0 if c.save() else 3


def cmd_checkpoint(c):
    c.need()
    st = c.state
    if c.a.objective is not None:
        st["objective"] = c.a.objective
    if c.a.next_text is not None:
        st["next"] = {"text": c.a.next_text, "paths": c.a.next_path}
    if c.a.note is not None:
        st["notes"] = c.a.note
    st["snapshot"] = dict(snapshot(c.root), taken=now())
    return 0 if c.save() else 3


def cmd_save(c):
    c.need()
    warn = check_graph(c.root, c.graph) + session_report(c.sessions, [d["path"] for d in snapshot(c.root)["dirty"]])
    if warn:
        print("Validation notes (not blocking):\n" + fmt_drift(warn) + "\n")
    return cmd_checkpoint(c)


def cmd_work(c):
    c.need()
    ev = {e["id"]: e for e in c.state["evidence"]}
    for i in c.a.evidence:
        if i not in ev:
            raise CBError(f"unknown evidence {i}; record one with `contextbridge run -- <cmd>`")
        if ev[i]["status"] != "passed":
            raise CBError(f"evidence {i} is {ev[i]['status']}, not passed; it cannot back a completed claim")
    if c.a.sub == "add":
        c.state["work"].append({"id": next_id(c.state["work"], "W"), "status": c.a.status, "text": c.a.text,
                                "paths": c.a.path, "evidence": c.a.evidence, "by": author(), "ts": now()})
    else:
        w = next((w for w in c.state["work"] if w["id"] == c.a.id), None)
        if not w:
            raise CBError(f"no work item {c.a.id}")
        w["status"] = c.a.status
        w["evidence"] = sorted(set(w.get("evidence", [])) | set(c.a.evidence))
        w["by"] = author()
    return 0 if c.save() else 3


def cmd_run(c):
    argv = c.a.argv[1:] if c.a.argv[:1] == ["--"] else c.a.argv
    if not argv:
        raise CBError("usage: contextbridge run [--timeout N] -- <command> [args]")
    c.need()
    snap = snapshot(c.root)
    ev = {"id": next_id(c.state["evidence"], "E"), "cmd": " ".join(argv), "status": "running", "exit": None,
          "ts": now(), "head": snap["head"], "fingerprint": snap["fingerprint"], "tail": ""}
    c.state["evidence"].append(ev)
    c.a.yes = True  # recording a command the user chose to run needs no separate review
    c.save(review=False)  # persisted first so an interrupted run stays visible as "never finished"
    t0 = time.time()
    try:
        r = subprocess.run(argv, cwd=c.root, capture_output=True, text=True, errors="replace", timeout=c.a.timeout)
        ev["exit"], out = r.returncode, (r.stdout + r.stderr)
        ev["status"] = "passed" if r.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        ev["exit"], out, ev["status"] = None, f"timed out after {c.a.timeout}s", "failed"
    except FileNotFoundError:
        ev["exit"], out, ev["status"] = 127, f"command not found: {argv[0]}", "failed"
    ev["tail"] = redact("\n".join(out.strip().splitlines()[-15:]))[-1500:]
    ev["seconds"] = round(time.time() - t0, 2)
    c.a.redact = True
    c.save(review=False)
    print(f"{ev['id']} `{ev['cmd']}` -> {ev['status'].upper()} (exit {ev['exit']}, {ev['seconds']}s)")
    return 0 if ev["status"] == "passed" else 1


def cmd_assume(c):
    c.need()
    c.state["assumptions"].append({"id": next_id(c.state["assumptions"], "A"), "text": c.a.text,
                                   "file": c.a.file, "contains": c.a.contains, "by": author()})
    return 0 if c.save() else 3


def cmd_decision(c):
    c.need()
    a = c.a
    did = add_decision(c.graph, a.title, a.why, a.rejected, a.requirement, a.code, a.test, a.depends, a.consequence)
    print(f"Decision {did} added.")
    return 0 if c.save({"DECISIONS.md": render_decisions(c.graph)}) else 3


def cmd_graph(c):
    c.need()
    s, a = c.a.sub, getattr(c.a, "arg", None)
    if s == "show":
        for k in sorted(c.graph["nodes"]):
            print(fmt_node(c.graph, k))
    elif s == "query":
        print("\n".join(query(c.graph, a)) or "No matches.")
    elif s == "trace":
        print("\n".join(trace(c.graph, a)))
    elif s == "check":
        f = check_graph(c.root, c.graph)
        print(fmt_drift(f))
        return 1 if any(l != "info" for l, _ in f) else 0
    else:
        return 0 if apply(c.root, {"DECISIONS.md": render_decisions(c.graph)}, c.a.yes, c.a.redact) else 3
    return 0


def cmd_drift(c):
    c.need()
    cur, f = drift(c.root, c.state, c.graph)
    f += session_report(c.sessions, [d["path"] for d in cur["dirty"]])
    if c.a.json:
        print(json.dumps([{"level": l, "message": m} for l, m in f], indent=2))
    else:
        print(fmt_drift(f))
    return 1 if any(l != "info" for l, _ in f) else 0


def cmd_status(c):
    c.need()
    st = c.state
    print(f"Objective: {st['objective'] or 'Unknown'}")
    for s, items in _sorted_status(st).items():
        print(f"{s.capitalize()}: {len(items)}" + "".join(f"\n  {w['id']} {w['text']}" for w in items))
    ev = [e for e in st["evidence"] if e["status"] != "running"]
    print(f"Test runs: {len(st['evidence'])} recorded, {sum(e['status'] == 'passed' for e in ev)} passed, "
          f"{sum(e['status'] == 'failed' for e in ev)} failed, {sum(e['status'] == 'running' for e in st['evidence'])} unfinished")
    if st["snapshot"]:
        print("\nDrift:")
        return cmd_drift(c)
    print("No checkpoint yet.")
    return 0


def cmd_resume(c):
    if not c.err:
        c.need()
    v, f, _ = gate(c.root, c.state, c.graph, c.sessions, c.err)
    if c.a.json:
        print(json.dumps({"verdict": v, "findings": [{"level": l, "message": m} for l, m in f]}, indent=2))
        return EXIT[v]
    print(f"## Resume safety gate: {v}\n{GATE_ADVICE[v]}\n\n{fmt_drift(f)}\n")
    if not c.a.check and c.state and c.state.get("snapshot") and v != "BLOCKED":
        print(render_handoff(c.state, c.graph))
        print(RESUME_RULES)
    return EXIT[v]


def cmd_session(c):
    c.need()
    ss = c.sessions["sessions"]
    if c.a.sub == "start":
        if any(s["name"] == c.a.name and s["status"] == "active" for s in ss):
            raise CBError(f"session {c.a.name} is already active")
        ss.append({"name": c.a.name, "task": c.a.task, "agent": c.a.agent, "claims": c.a.claim,
                   "depends_on": c.a.depends, "status": "active", "started": now()})
    elif c.a.sub == "finish":
        s = next((s for s in ss if s["name"] == c.a.name and s["status"] == "active"), None)
        if not s:
            raise CBError(f"no active session {c.a.name}")
        s["status"] = "finished"
    else:
        dirty = [d["path"] for d in snapshot(c.root)["dirty"]]
        for s in ss:
            print(f"{s['name']} [{s['status']}] agent={s['agent']} claims={s['claims']} task={s['task']!r}")
        f = session_report(c.sessions, dirty)
        print("Advisory only (cannot prevent conflicts across clones/machines):\n" + (fmt_drift(f) if f else "no overlaps detected"))
        return 1 if any(l == "warn" for l, _ in f) else 0
    return 0 if c.save() else 3


def cmd_export(c):
    c.need()
    bundle = dump({"schema": SCHEMA, "exported": now(), "state": c.state, "graph": c.graph, "sessions": c.sessions})
    hits = scan(bundle)
    if hits and not c.a.redact:
        raise CBError("refusing to export: possible secret(s): " + ", ".join(f"{n} (line {l})" for n, l in hits[:5])
                      + ". Re-run with --redact.")
    Path(c.a.output).write_text(redact(bundle) if hits else bundle, encoding="utf-8")
    print(f"Wrote {c.a.output} ({len(bundle)} bytes, scanned: {len(hits)} secret(s) {'redacted' if hits else 'found'}).")
    return 0


def cmd_import(c):
    try:
        b = json.loads(Path(c.a.bundle).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise CBError(f"cannot read bundle: {e}")
    if b.get("schema") != SCHEMA:
        raise CBError(f"unsupported bundle schema {b.get('schema')!r}")
    c.need()
    c.state, c.graph, c.sessions = b["state"], b["graph"], b["sessions"]
    print("Imported notes are untrusted data; run `contextbridge drift` before relying on them.")
    return 0 if c.save() else 3


def cmd_scan(c):
    bad = 0
    for p in c.a.paths:
        for n, line in scan(Path(p).read_text(encoding="utf-8", errors="replace")):
            print(f"{p}:{line}: {n}")
            bad += 1
    print(f"{bad} possible secret(s) found." if bad else "No secrets detected.")
    return 2 if bad else 0


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        if hasattr(st, "reconfigure"):
            st.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    a = build().parse_args(argv)
    try:
        return globals()[f"cmd_{a.cmd}"](Ctx(a))
    except CBError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code
