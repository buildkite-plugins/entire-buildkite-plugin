"""Exercise the hook with the real agent/Git, a local API, and fake credentials."""

import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
URL = "entire://region.entire.io/et/project/repository"
TOKEN = "job-token-sentinel"
AGENT_TOKEN = "agent-session-secret-sentinel"
REF = "0123456789abcdef0123456789abcdef01234567"


class PluginTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "home"
        self.home.mkdir()
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        # Keep host Entire installations out of these tests.
        for name in ("bash", "buildkite-agent", "curl", "git", "sed", "mkdir", "cp", "dirname",
                     "uname", "mktemp", "sha256sum", "tar", "gzip", "rm"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.env = {
            "PATH": str(self.bin), "HOME": str(self.home), "TMPDIR": str(self.directory),
            "BUILDKITE_REPO": URL, "BUILDKITE_JOB_ID": "job-123",
            "BUILDKITE_AGENT_ACCESS_TOKEN": AGENT_TOKEN,
            "ENTIRE_TOKEN": "personal-token-must-be-replaced",
            "EXPECTED_TOKEN": TOKEN,
        }
        self.script(self.bin / "git-remote-entire", f"""#!/bin/sh
[ "$ENTIRE_TOKEN" = "$EXPECTED_TOKEN" ] || exit 1
while read -r line; do
  case "$line" in
    capabilities) printf '\\n' ;;
    list) printf '{REF} refs/heads/main\\n\\n' ;;
    '') exit 0 ;;
    *) exit 1 ;;
  esac
done
""")
        self.requests = []
        self.response = (200, json.dumps({"token": TOKEN}))
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                owner.requests.append((self.path, self.headers["Authorization"], json.loads(body)))
                status, body = owner.response
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body.encode())

            def log_message(self, *_):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.env["BUILDKITE_AGENT_ENDPOINT"] = f"http://127.0.0.1:{server.server_port}/v3"

    def script(self, path, source):
        path.write_text(source)
        path.chmod(0o755)

    def hook(self, command='git ls-remote "$BUILDKITE_REPO"'):
        return subprocess.run([
            shutil.which("bash"), "-x", "-c", '''
source "$1/hooks/environment"
[[ "$BUILDKITE_REPO" == "$2" ]]
eval "$3"
''', "test", str(ROOT), self.env["BUILDKITE_REPO"],
            command,
        ], env=self.env, cwd=self.directory, text=True, capture_output=True, timeout=240)

    def assert_secret_free(self, result):
        for secret in (TOKEN, AGENT_TOKEN):
            self.assertNotIn(secret, result.stdout + result.stderr)
            for path in self.home.rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret.encode(), path.read_bytes())

    def test_existing_install_and_standard_repo_use_job_credentials(self):
        for url in (URL, URL + ".git"):
            self.env["BUILDKITE_REPO"] = url
            result = self.hook()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), f"{REF}\trefs/heads/main")
            self.assert_secret_free(result)
        # This is a lookup alias, not the listed HTTPS clone URL ending in .git.
        # Nor should a native URL's existing .git suffix be removed.
        self.assertEqual(self.requests, [
            ("/v3/jobs/job-123/repository_access_token", f"Token {AGENT_TOKEN}",
             {"repo_url": "https://region.entire.io/et/project/repository"}),
            ("/v3/jobs/job-123/repository_access_token", f"Token {AGENT_TOKEN}",
             {"repo_url": "https://region.entire.io/et/project/repository.git"})
        ])
        self.assertFalse((self.home / ".local").exists())

    def test_install_is_left_in_place_and_reused(self):
        (self.bin / "git-remote-entire").unlink()
        archive = os.environ.get("ENTIRE_TEST_ARCHIVE")
        curl = shutil.which("curl")
        (self.bin / "curl").unlink()
        self.env["TEST_ARCHIVE"] = str(Path(archive).resolve()) if archive else ""
        self.script(self.bin / "curl", f"""#!/bin/bash
printf '%s\\n' "$@" >> "$HOME/curl-argv"
if [[ -n "$TEST_ARCHIVE" ]]; then
  cp "$TEST_ARCHIVE" "${{@: -1}}"
  exit
fi
exec {curl} "$@"
""")
        command = 'git-remote-entire --version; [[ "$ENTIRE_TOKEN" == "$EXPECTED_TOKEN" ]]'
        result = self.hook(command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Installing git-remote-entire", result.stdout)
        self.assertIn("git-remote-entire 0.0.0+57de2c3", result.stdout)
        self.assert_secret_free(result)
        helper = self.home / ".local/bin/git-remote-entire"
        installed = helper.stat()
        self.assertFalse((self.home / ".local/bin/entire").exists())
        # A new hook process must discover the persisted installation.
        result = self.hook(command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Installing git-remote-entire", result.stdout)
        self.assertIn("git-remote-entire 0.0.0+57de2c3", result.stdout)
        self.assert_secret_free(result)
        self.assertEqual(helper.stat().st_ino, installed.st_ino)
        self.assertEqual(helper.stat().st_mtime_ns, installed.st_mtime_ns)
        self.assertEqual((self.home / "curl-argv").read_text().count("git-remote-entire_linux_"), 1)

    def test_corrupt_download_does_not_install(self):
        (self.bin / "git-remote-entire").unlink()
        (self.bin / "curl").unlink()
        self.script(self.bin / "curl", '#!/bin/bash\nprintf corrupt > "${@: -1}"\n')
        result = self.hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum mismatch", result.stderr)
        self.assertFalse((self.home / ".local").exists())
        self.assertEqual(self.requests, [])

    def test_credential_errors_and_invalid_tokens_fail_without_leaking(self):
        for status, body in [(401, json.dumps({"message": TOKEN})),
                             (403, json.dumps({"message": TOKEN})),
                             (200, "not-json " + TOKEN), (200, '{}'),
                             (200, '{"token":""}'), (200, '{"token":null}'),
                             (200, '{"token":"fail"}')]:
            with self.subTest(status=status, body=body):
                self.response = status, body
                result = self.hook()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(REF, result.stdout)
                self.assert_secret_free(result)
        self.assertEqual(len(self.requests), 7)

    def test_invalid_repo_cannot_inject_credential_fields(self):
        for url in ("https://region.entire.io/et/p/r.git", "entire://region.entire.io",
                    "entire://region.entire.io/et/p/r\nhost=other.entire.io"):
            self.env["BUILDKITE_REPO"] = url
            result = self.hook()
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.requests, [])

    def test_agent_runs_plugin_environment_before_checkout_without_git_credentials_config(self):
        plugin = self.directory / "plugin"
        shutil.copytree(ROOT / "hooks", plugin / "hooks")
        subprocess.run(["git", "init", "-q", str(plugin)], env=self.env, check=True)
        subprocess.run(["git", "-C", str(plugin), "add", "."], env=self.env, check=True)
        subprocess.run(["git", "-C", str(plugin), "-c", "user.name=Test", "-c",
                        "user.email=test@example.com", "-c", "commit.gpgsign=false",
                        "commit", "-qm", "Test plugin"], env=self.env, check=True)
        # Test-only source mapping: exercise normal external-plugin hook timing.
        (self.home / ".gitconfig").write_text(
            f'[url "file://{plugin}"]\n  insteadOf = https://github.com/sj26/entire-buildkite-plugin\n')
        hooks = self.directory / "agent-hooks"
        hooks.mkdir()
        self.script(hooks / "pre-checkout", '''#!/bin/bash
set -eu
[[ "$ENTIRE_TOKEN" == "$EXPECTED_TOKEN" ]]
if git config --get credential.helper; then exit 1; fi
echo 'Token ready before pre-checkout'
''')
        self.script(hooks / "checkout", "#!/bin/sh\nexit 0\n")
        checkout = self.directory / "checkout"
        checkout.mkdir()
        env = self.env | {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "BUILDKITE_BUILD_CHECKOUT_PATH": str(checkout),
            "BUILDKITE_BUILD_PATH": str(self.directory / "builds"),
            "BUILDKITE_SOCKETS_PATH": str(self.directory / "sockets"),
            "BUILDKITE_PLUGINS_PATH": str(self.directory / "plugins"),
            "BUILDKITE_ORGANIZATION_SLUG": "test",
            "BUILDKITE_PIPELINE_SLUG": "test",
            "BUILDKITE_PIPELINE_PROVIDER": "custom",
            "BUILDKITE_AGENT_NAME": "test", "BUILDKITE_COMMIT": REF,
            "BUILDKITE_BRANCH": "main", "GIT_CONFIG_NOSYSTEM": "1",
        }
        result = subprocess.run([
            "buildkite-agent", "bootstrap", "--no-job-api", "--plugins-enabled",
            "--command-eval", "--plugins", '[{"github.com/sj26/entire-buildkite-plugin":{}}]',
            "--hooks-path", str(hooks), "--command", 'git ls-remote "$BUILDKITE_REPO"',
        ], env=env, cwd=checkout, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token ready before pre-checkout", result.stdout)
        self.assertIn(f"{REF}\trefs/heads/main", result.stdout)
        self.assert_secret_free(result)


if __name__ == "__main__":
    unittest.main()
