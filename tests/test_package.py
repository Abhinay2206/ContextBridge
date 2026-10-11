import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def test_plugin_manifest_is_valid(self):
        manifest = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(manifest["name"], "contextbridge")
        self.assertTrue(manifest["version"])

    def test_skill_frontmatter_and_required_fields(self):
        skill = (ROOT / "skills/contextbridge/SKILL.md").read_text()
        self.assertTrue(skill.startswith("---\n"))
        frontmatter = skill.split("---", 2)[1]
        self.assertRegex(frontmatter, r"(?m)^name: contextbridge$")
        self.assertRegex(frontmatter, r"(?m)^description: .+")
        self.assertIn("Never store credentials", skill)
        self.assertIn("Workflow: checkpoint", skill)
        self.assertIn("Workflow: resume", skill)

    def test_commands_exist_and_have_frontmatter(self):
        for name in ("init", "checkpoint", "resume", "status"):
            path = ROOT / "commands" / f"{name}.md"
            self.assertTrue(path.exists(), f"Missing command: {name}")
            content = path.read_text()
            self.assertTrue(content.startswith("---\n"), name)
            self.assertIn("description:", content, name)

    def test_all_context_templates_exist(self):
        for name in ("PROJECT", "ARCHITECTURE", "DECISIONS", "STATE", "NEXT", "HANDOFF"):
            path = ROOT / "templates/context" / f"{name}.md"
            self.assertTrue(path.exists(), f"Missing template: {name}")
            self.assertGreater(len(path.read_text().strip()), 30)

    def test_security_and_limitations_are_documented(self):
        readme = (ROOT / "README.md").read_text().lower()
        security = (ROOT / "SECURITY.md").read_text().lower()
        self.assertIn("does not transfer chats", readme)
        self.assertIn("never store", security)
        self.assertIn("no server", security)
        self.assertIn("best-effort", security)

    def test_manual_test_plan_exists(self):
        plan = (ROOT / "tests/TEST_PLAN.md").read_text()
        self.assertGreaterEqual(len(re.findall(r"(?m)^## Test \d+", plan)), 6)


if __name__ == "__main__":
    unittest.main()
