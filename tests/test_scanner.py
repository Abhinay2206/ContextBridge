"""Unit tests for the secret scanner: dedicated patterns, look-alikes that must stay clean, and redaction."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from contextbridge.core import redact, scan  # noqa: E402

# Fake, format-valid values assembled from pieces so this file does not itself look like a leaked key.
A36 = "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1dE3fG5"
SECRETS = {
    "stripe-key": "STRIPE=" + "sk_" + "live_" + "4eC39HqLyjWDarjtT1zdp7dc",
    "sendgrid-key": "key " + "SG." + "ngeVfQFYQlKU0ufo8x5d1A" + "." + "TwL2iGABf9DHoTf-09kqeF8tAmbihYzrnopKc-1s5cr",
    "github-fine-grained-token": "token0 = " + "github_pat_" + "11ABCDEFG0aBcDeFgHiJkL_" + "mNoPqRsTuVwXyZ0123456789aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567",
    "npm-token": "//registry.npmjs.org/:_authToken=" + "npm_" + A36,
    "twilio-key": "TW " + "SK" + "0123456789abcdef0123456789abcdef",
    "azure-key": "DefaultEndpointsProtocol=https;AccountName=a;AccountKey=" + "dGhpcyBpcyBhIGZha2UgYXp1cmUga2V5IGZvciB0ZXN0cw==",
    "url-password": "DATABASE_URL=postgres://admin:" + "s3cr3tPass" + "@db.internal:5432/app",
    "google-api-key": "k=" + "AIza" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6-",
    "aws-access-key": "AKIA" + "IOSFODNN7EXAMPL3",
    "gitlab-token": "glpat-" + "aB3dE5gH7jK9mN1pQ3sT",
    "huggingface-token": "hf_" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1dE3f",
    "digitalocean-token": "dop_" + "v1_" + "0123456789abcdef" * 4,
    "shopify-token": "shp" + "at_" + "0123456789abcdef0123456789abcdef",
    "mailchimp-key": "0123456789abcdef0123456789abcdef" + "-us12",
    "telegram-bot-token": "123456789" + ":" + "AAH_aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1d",
    "pypi-token": "pypi-" + "AgEIcHlwaS5vcmc" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1dE3fG5hI7jK9mN1pQ3sT5vW7yZ9",
}
CLEAN = [
    "commit 9fceb02d0ae598e95dc970b74767f19372d61af8", "id = 550e8400-e29b-41d4-a716-446655440000", "token_count = 128",
    "password: str", "secret_key = os.environ['SECRET_KEY']", "https://github.com/Abhinay2206/ContextBridge",
    "http://localhost:8080/path", "git@github.com:org/repo.git", "https://user@example.com/x", "SKIP_TESTS=1",
    "token = self._fp.read(1)[0]", "password = self._decode_base64(arg)", "smtp.user, smtp.password = sim_auth[0], sim_auth[1]",
    "let token = params[0].toLowerCase();", "secret_key = os.environ[\"SECRET_KEY\"]", "api_key = get_api_key_from_vault()",
    "tokenizer = AutoTokenizer.from_pretrained(name)", "access_token = response.json()['access_token']", "password: str = field(default=None)",
    "see sk_live in the docs", "npm install npm_package", "postgres://localhost:5432/app",
]


class ScannerTests(unittest.TestCase):
    def test_each_secret_type_is_detected_by_its_own_pattern(self):
        for name, text in SECRETS.items():
            self.assertIn(name, [n for n, _ in scan(text)], f"{name} not detected in {text!r}")

    def test_lookalikes_are_not_flagged(self):
        for text in CLEAN:
            self.assertEqual(scan(text), [], text)

    def test_redaction_removes_the_secret_and_leaves_clean_text(self):
        for name, text in SECRETS.items():
            out = redact(text)
            self.assertEqual(scan(out), [], f"{name}: still detected after redact: {out!r}")
            self.assertIn("[REDACTED", out)

    def test_quoted_literals_are_still_caught_even_with_punctuation(self):
        for t in ('password = "my(pass)word1"', "api_key: 'ab12cd34ef56'", 'AUTH_TOKEN=abc123XYZ789def456'):
            self.assertTrue(scan(t), t)

    def test_url_password_redaction_keeps_the_rest_of_the_url(self):
        out = redact(SECRETS["url-password"])
        self.assertIn("postgres://admin:", out)
        self.assertIn("@db.internal:5432/app", out)
        self.assertNotIn("s3cr3tPass", out)


if __name__ == "__main__":
    unittest.main()
