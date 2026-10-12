"""End-to-end: drives the real CLI against throwaway git repos."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / "src")
ENV = dict(os.environ, PYTHONPATH=SRC, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


class Repo:
    def __init__(self, clone_of=None):
        self._t = tempfile.TemporaryDirectory()
        self.p = Path(self._t.name)
        if clone_of:  # a real clone shares history, like a second machine/account
            self.sh("git", "clone", "-q", str(clone_of.p), ".")
            return
        self.sh("git", "init", "-q", "-b", "main")
        self.write("app.py", "print('v1')\n")
        self.sh("git", "add", "."), self.sh("git", "commit", "-qm", "init")

    def __del__(self):
        self._t.cleanup()

    def sh(self, *a):
        return subprocess.run(a, cwd=self.p, capture_output=True, text=True, encoding="utf-8", env=ENV)

    def cb(self, *a, yes=True):
        return subprocess.run([sys.executable, "-m", "contextbridge", *a, *(["--yes"] if yes else [])],
                              cwd=self.p, capture_output=True, text=True, encoding="utf-8", env=ENV, stdin=subprocess.DEVNULL)

    def write(self, name, text):
        f = self.p / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")

    def state(self):
        return json.loads((self.p / "contextbridge/state.json").read_text(encoding="utf-8"))


class E2E(unittest.TestCase):
    def setUp(self):
        self.r = Repo()

    def test_verified_state_and_drift(self):
        r = self.r
        r.write("app.py", "print('v2')\n")  # uncommitted edit
        self.assertEqual(r.cb("work", "add", "refactor app", "--status", "planned", "--path", "app.py").returncode, 0)
        self.assertEqual(r.cb("checkpoint", "--objective", "ship v2", "--next", "finish app", "--next-path", "app.py").returncode, 0)
        s = r.state()["snapshot"]
        self.assertEqual(s["branch"], "main")
        self.assertEqual([d["path"] for d in s["dirty"]], ["app.py"])
        self.assertIn("planned", (r.p / "contextbridge/HANDOFF.md").read_text(encoding="utf-8").lower())
        # own notes never count as drift; unverified state is still flagged
        d = r.cb("drift")
        self.assertNotIn("contextbridge/", d.stdout)
        self.assertIn("no test runs recorded", d.stdout)
        # real execution recorded as evidence
        self.assertEqual(r.cb("run", "--", sys.executable, "-c", "print('ok')").returncode, 0)
        self.assertEqual(r.cb("run", "--", sys.executable, "-c", "raise SystemExit(3)").returncode, 1)
        ev = r.state()["evidence"]
        self.assertEqual([e["status"] for e in ev], ["passed", "failed"])
        self.assertIn("FAILED", r.cb("drift").stdout)
        # drift: edit after checkpoint, new commit, branch switch
        r.write("app.py", "print('v3')\n")
        r.write("new.py", "x=1\n")
        out = r.cb("drift").stdout
        self.assertIn("app.py: edited after checkpoint", out)
        self.assertIn("new.py: new uncommitted change", out)
        self.assertIn("W1 (planned)", out)  # planned task's file changed -> may be started
        self.assertIn("(planned) 'finish app'", out)
        r.sh("git", "checkout", "-qb", "feature")
        self.assertIn("branch changed: main -> feature", r.cb("drift").stdout)
        self.assertEqual(r.cb("drift").returncode, 1)
        r.sh("git", "add", "."), r.sh("git", "commit", "-qm", "work")
        self.assertIn("commit(s) since checkpoint", r.cb("drift").stdout)

    def test_clean_checkpoint_with_passing_test_has_no_drift(self):
        r = self.r
        r.cb("checkpoint", "--objective", "x")
        r.cb("run", "--", sys.executable, "-c", "pass")
        r.cb("checkpoint")  # re-snapshot so evidence matches state
        d = r.cb("drift")
        self.assertEqual(d.returncode, 0, d.stdout)

    def test_review_gate_is_dry_run_without_yes(self):
        r = self.r
        p = r.cb("checkpoint", "--objective", "x", yes=False)
        self.assertEqual(p.returncode, 3)
        self.assertIn("+++ b/contextbridge/state.json", p.stdout)
        self.assertFalse((r.p / "contextbridge").exists())

    def test_secrets_refused_then_redacted_and_excluded_files_hidden(self):
        r = self.r
        key = "AKIA" + "ABCDEFGHIJKLMNOP"
        p = r.cb("checkpoint", "--note", f"aws {key}")
        self.assertEqual(p.returncode, 2)
        self.assertNotIn(key, p.stdout + p.stderr)
        self.assertEqual(r.cb("checkpoint", "--note", f"aws {key}", "--redact").returncode, 0)
        blob = "".join(f.read_text(encoding="utf-8") for f in (r.p / "contextbridge").iterdir())
        self.assertNotIn(key, blob)
        r.write(".env", "TOKEN=abc12345xyz\n")
        r.write("server.pem", "x")
        r.cb("checkpoint")
        s = r.state()["snapshot"]
        self.assertEqual(s["excluded"], 2)
        self.assertNotIn(".env", json.dumps(s))
        self.assertEqual(r.cb("scan", ".env").returncode, 2)

    def test_command_output_secrets_are_redacted(self):
        r = self.r
        r.cb("run", "--", sys.executable, "-c", "print('token=' + 'Zx9' * 5 + '1')")
        self.assertNotIn("Zx9Zx9", json.dumps(r.state()))

    def test_decision_graph_query_trace_and_check(self):
        r = self.r
        r.write("src/queue.py", "redis\n")
        r.write("tests/test_queue.py", "pass\n")
        self.assertEqual(r.cb("decision", "add", "Use Redis for job queue", "--why", "need atomic BRPOPLPUSH",
                              "--rejected", "Postgres LISTEN/NOTIFY: no durable ack",
                              "--requirement", "Jobs survive worker crash", "--code", "src/queue.py:enqueue",
                              "--test", "tests/test_queue.py", "--consequence", "Redis must be persistent").returncode, 0)
        q = r.cb("graph", "query", "redis").stdout
        self.assertIn("D1", q)
        self.assertIn("implemented_in", q)
        t = r.cb("graph", "trace", "D1").stdout
        for want in ("Jobs survive worker crash", "src/queue.py:enqueue", "tests/test_queue.py"):
            self.assertIn(want, t)
        self.assertIn("Postgres LISTEN/NOTIFY", (r.p / "contextbridge/DECISIONS.md").read_text(encoding="utf-8"))
        self.assertEqual(r.cb("graph", "check").returncode, 0)
        (r.p / "src/queue.py").unlink()
        c = r.cb("graph", "check")
        self.assertEqual(c.returncode, 1)
        self.assertIn("file no longer exists", c.stdout)

    def test_assumption_goes_stale(self):
        r = self.r
        r.cb("assume", "app prints v1", "--file", "app.py", "--contains", "v1")
        r.cb("checkpoint")
        self.assertNotIn("assumption", r.cb("drift").stdout.lower().replace("no test", ""))
        r.write("app.py", "print('v9')\n")
        self.assertIn("A1 'app prints v1'", r.cb("drift").stdout)

    def test_sessions_detect_overlap_and_are_advisory(self):
        r = self.r
        r.cb("session", "start", "auth", "--claim", "src/auth/")
        r.cb("session", "start", "api", "--claim", "src/auth/policy.py", "--claim", "src/api/", "--depends", "auth")
        r.write("src/auth/policy.py", "x\n")
        o = r.cb("session", "list")
        self.assertEqual(o.returncode, 1)
        self.assertIn("overlapping paths", o.stdout)
        self.assertIn("both claims cover modified files", o.stdout)
        self.assertIn("Advisory only", o.stdout)
        r.cb("session", "finish", "auth")
        self.assertEqual(r.cb("session", "list").returncode, 0)

    def test_portability_export_import_resume_in_fresh_clone(self):
        r = self.r
        r.cb("decision", "add", "Use SQLite", "--why", "zero ops")
        r.cb("work", "add", "schema", "--status", "completed")
        r.cb("work", "add", "tried migrations", "--status", "attempted")
        r.cb("checkpoint", "--objective", "port me", "--next", "write API")
        self.assertEqual(r.cb("export", "-o", str(r.p / "bundle.json"), yes=False).returncode, 0)
        clone = Repo(clone_of=r)  # different machine/account stand-in
        self.assertEqual(clone.cb("import", str(r.p / "bundle.json")).returncode, 0)
        out = clone.cb("resume").stdout
        for want in ("port me", "schema", "tried migrations", "Attempted (not confirmed working)", "Use SQLite",
                     "Resume safety gate", "untrusted data"):
            self.assertIn(want, out)

    def test_local_only_init_excludes_dir(self):
        r = self.r
        r.cb("init", "--local-only")
        self.assertIn("contextbridge/", (r.p / ".git/info/exclude").read_text(encoding="utf-8"))
        self.assertEqual(r.sh("git", "status", "--porcelain").stdout.strip(), "?? .contextbridgeignore")

    def test_works_without_git(self):
        with tempfile.TemporaryDirectory() as d:
            run = lambda *a: subprocess.run([sys.executable, "-m", "contextbridge", *a, "--yes"], cwd=d,
                                            capture_output=True, text=True, encoding="utf-8", env=ENV, stdin=subprocess.DEVNULL)
            self.assertEqual(run("checkpoint").returncode, 0)
            self.assertIn("git unavailable", run("drift").stdout)

    # ---- 0.3.0: resume safety gate, provenance, save
    def _ready_repo(self):
        r = self.r
        r.cb("run", "--", sys.executable, "-c", "pass")
        r.cb("work", "add", "base", "--status", "completed", "--evidence", "E1")
        r.cb("checkpoint", "--objective", "o", "--next", "n")
        return r

    def test_gate_ready_review_blocked(self):
        r = self._ready_repo()
        g = r.cb("resume", "--check")
        self.assertEqual((g.returncode, "READY" in g.stdout), (0, True), g.stdout)
        r.write("app.py", "print('changed')\n")  # edit after checkpoint
        g = r.cb("resume", "--check")
        self.assertEqual(g.returncode, 1)
        self.assertIn("REVIEW_REQUIRED", g.stdout)
        self.assertIn("Do not edit yet", g.stdout)
        r.sh("git", "checkout", "-qb", "other")
        g = r.cb("resume")
        self.assertEqual(g.returncode, 2)
        self.assertIn("BLOCKED", g.stdout)
        self.assertNotIn("Rules for the resuming agent", g.stdout)  # no prompt when blocked

    def test_gate_json_and_missing_or_corrupt_state(self):
        r = self.r
        g = r.cb("resume", "--json")
        self.assertEqual(g.returncode, 2)
        self.assertEqual(json.loads(g.stdout)["verdict"], "BLOCKED")
        r.cb("checkpoint")
        (r.p / "contextbridge/state.json").write_text("{not json", encoding="utf-8")
        g = r.cb("resume", "--check")
        self.assertEqual(g.returncode, 2)
        self.assertIn("not valid JSON", g.stdout)
        (r.p / "contextbridge/state.json").write_text(json.dumps({"schema": "other/9"}), encoding="utf-8")
        self.assertIn("unsupported schema", r.cb("resume", "--check").stdout)

    def test_gate_full_resume_prompt_when_ready(self):
        out = self._ready_repo().cb("resume").stdout
        self.assertLess(out.index("Resume safety gate: READY"), out.index("# Session Handoff"))
        self.assertIn("Rules for the resuming agent", out)

    def test_provenance_claimed_vs_verified(self):
        r = self.r
        env = dict(ENV, CONTEXTBRIDGE_AGENT="claude-acct-a")
        run = lambda *a: subprocess.run([sys.executable, "-m", "contextbridge", *a, "--yes"], cwd=r.p, capture_output=True,
                                        text=True, encoding="utf-8", env=env, stdin=subprocess.DEVNULL)
        run("run", "--", sys.executable, "-c", "pass")
        run("run", "--", sys.executable, "-c", "raise SystemExit(1)")
        run("work", "add", "backed", "--status", "completed", "--evidence", "E1")
        run("work", "add", "bare claim", "--status", "completed")
        bad = run("work", "add", "bad", "--status", "completed", "--evidence", "E2")  # failed run can't back a claim
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(run("work", "add", "x", "--evidence", "E99").returncode, 2)
        run("checkpoint")
        h = (r.p / "contextbridge/HANDOFF.md").read_text(encoding="utf-8")
        self.assertIn("W1: backed — verified by E1 PASSED exit 0", h)
        self.assertIn("W2: bare claim — claimed by claude-acct-a, no linked evidence", h)
        self.assertIn("observed", h)
        self.assertIn("only a claim by claude-acct-a", run("drift").stdout)

    # ---- 0.3.2 fixes
    def test_nested_repo_changes_are_detected(self):
        r = self.r
        n = r.p / "vendor" / "lib"
        n.mkdir(parents=True)
        for c in ("git init -q -b main", "git add -A", "git commit -qm n"):
            if c == "git add -A": (n / "x.py").write_text("1\n", encoding="utf-8")
            subprocess.run(c, shell=True, cwd=n, env=ENV, capture_output=True)
        r.cb("run", "--", sys.executable, "-c", "pass")
        r.cb("checkpoint", "--objective", "o")
        snap = r.state()["snapshot"]["dirty"]
        self.assertEqual([(d["path"], d["status"]) for d in snap], [("vendor/lib/", "nested-repo")])
        self.assertEqual(r.cb("resume", "--check").returncode, 0)  # untouched nested repo: no false alarm
        (n / "x.py").write_text("CHANGED\n", encoding="utf-8")
        subprocess.run("git commit -qam more", shell=True, cwd=n, env=ENV, capture_output=True)
        g = r.cb("resume", "--check")
        self.assertEqual(g.returncode, 1, g.stdout)
        self.assertIn("vendor/lib/", g.stdout)

    def test_handoff_is_capped_but_state_keeps_everything(self):
        r = self.r
        r.cb("checkpoint", "--objective", "o")
        st = r.state()
        st["work"] = [dict(id=f"W{i}", status="completed", text=f"task {i}", paths=[], evidence=[], by="x", ts="t") for i in range(1, 201)]
        (r.p / "contextbridge/state.json").write_text(json.dumps(st), encoding="utf-8")
        r.cb("checkpoint")
        h = (r.p / "contextbridge/HANDOFF.md").read_text(encoding="utf-8")
        self.assertIn("W200:", h)
        self.assertNotIn("W1:", h)
        self.assertIn("175 older item(s) not shown", h)
        self.assertLess(len(h), 8000)
        self.assertEqual(len(r.state()["work"]), 200)
        out = r.cb("resume", "--check").stdout
        self.assertIn("197 more completed items are only claims", out)
        self.assertLess(len(out), 2500)

    def test_status_with_checkpoint_does_not_crash(self):
        r = self.r
        self.assertIn("No checkpoint yet", r.cb("status").stdout)
        r.cb("checkpoint", "--objective", "obj")
        s = r.cb("status")
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertIn("Objective: obj", s.stdout)
        self.assertNotIn("Traceback", s.stderr)

    def test_save_reports_validation_notes_then_checkpoints(self):
        r = self.r
        r.cb("decision", "add", "D", "--why", "w", "--code", "gone.py")
        s = r.cb("save", "--objective", "o")
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertIn("Validation notes", s.stdout)
        self.assertIn("gone.py", s.stdout)
        self.assertEqual(r.state()["objective"], "o")


if __name__ == "__main__":
    unittest.main()
