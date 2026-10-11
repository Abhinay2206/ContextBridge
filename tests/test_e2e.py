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
    def __init__(self):
        self._t = tempfile.TemporaryDirectory()
        self.p = Path(self._t.name)
        self.sh("git", "init", "-q", "-b", "main")
        self.write("app.py", "print('v1')\n")
        self.sh("git", "add", "."), self.sh("git", "commit", "-qm", "init")

    def __del__(self):
        self._t.cleanup()

    def sh(self, *a):
        return subprocess.run(a, cwd=self.p, capture_output=True, text=True, env=ENV)

    def cb(self, *a, yes=True):
        return subprocess.run([sys.executable, "-m", "contextbridge", *a, *(["--yes"] if yes else [])],
                              cwd=self.p, capture_output=True, text=True, env=ENV, stdin=subprocess.DEVNULL)

    def write(self, name, text):
        f = self.p / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)

    def state(self):
        return json.loads((self.p / "contextbridge/state.json").read_text())


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
        self.assertIn("planned", (r.p / "contextbridge/HANDOFF.md").read_text().lower())
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
        blob = "".join(f.read_text() for f in (r.p / "contextbridge").iterdir())
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
        self.assertIn("Postgres LISTEN/NOTIFY", (r.p / "contextbridge/DECISIONS.md").read_text())
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
        clone = Repo()  # different machine/account stand-in
        self.assertEqual(clone.cb("import", str(r.p / "bundle.json")).returncode, 0)
        out = clone.cb("resume").stdout
        for want in ("port me", "schema", "tried migrations", "Attempted (not confirmed working)", "Use SQLite",
                     "Drift since checkpoint", "untrusted data"):
            self.assertIn(want, out)

    def test_local_only_init_excludes_dir(self):
        r = self.r
        r.cb("init", "--local-only")
        self.assertIn("contextbridge/", (r.p / ".git/info/exclude").read_text())
        self.assertEqual(r.sh("git", "status", "--porcelain").stdout.strip(), "?? .contextbridgeignore")

    def test_works_without_git(self):
        with tempfile.TemporaryDirectory() as d:
            run = lambda *a: subprocess.run([sys.executable, "-m", "contextbridge", *a, "--yes"], cwd=d,
                                            capture_output=True, text=True, env=ENV, stdin=subprocess.DEVNULL)
            self.assertEqual(run("checkpoint").returncode, 0)
            self.assertIn("git unavailable", run("drift").stdout)


if __name__ == "__main__":
    unittest.main()
