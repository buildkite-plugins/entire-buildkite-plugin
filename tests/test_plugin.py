"""Exercise the installation hook and the real helper's native credential lookup."""

import hashlib
import http.server
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a564a68c802d50a0f4cff333da6ee13d59be027d"
VERSION = f"0.0.0+{COMMIT}"
URL = "entire://region.entire.io/et/project/repository"
TOKEN = "test-job-credential"


class PluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.download = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.download.cleanup)
        arch = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
        cls.archive = Path(os.environ.get("ENTIRE_TEST_ARCHIVE", f"{cls.download.name}/helper.tar.gz"))
        if not cls.archive.exists():
            subprocess.run(["curl", "-qfsSL", "--proto", "=https", "--proto-redir", "=https",
                            f"https://entire-public-release-bucket-7f3e2a01c9b48d56.s3.us-east-2.amazonaws.com/commit/{COMMIT}/git-remote-entire_linux_{arch}.tar.gz",
                            "-o", str(cls.archive)], check=True, timeout=180)
        # Test the compatibility promise against the released agent, not a mock.
        archive = Path(cls.download.name) / "agent.tar.gz"
        subprocess.run(["curl", "-qfsSL", "--proto", "=https", "--proto-redir", "=https",
                        f"https://github.com/buildkite/agent/releases/download/v4.3.0/buildkite-agent-linux-{arch}-4.3.0.tar.gz",
                        "-o", str(archive)], check=True, timeout=180)
        checksum = {"amd64": "f1ee66bdd4c052beebdc406ba5eb1b4246dc740c6872e8d3017ae53c527872b8",
                    "arm64": "bbd2b19589f2b50eee3c1e0730af96a2f695e0134653fb676553768ea89ed710"}[arch]
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == checksum
        cls.agent = Path(cls.download.name) / "buildkite-agent"
        with tarfile.open(archive) as tar:
            cls.agent.write_bytes(tar.extractfile("./buildkite-agent").read())
        cls.agent.chmod(0o755)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.installed = self.home / ".local/bin/git-remote-entire"
        # Do not pick up a host helper, Git configuration, or credentials.
        for name in ("bash", "git", "sort", "mkdir", "cp", "uname", "mktemp", "sed", "cat",
                     "sha256sum", "tar", "gzip", "rm", "mv", "readlink"):
            (self.bin / name).symlink_to(shutil.which(name))
        (self.bin / "buildkite-agent").symlink_to(self.agent)
        self.env = {"HOME": str(self.home), "PATH": str(self.bin),
                    "GIT_CONFIG_NOSYSTEM": "1", "TEST_ARCHIVE": str(self.archive),
                    "BUILDKITE_REPO": URL, "GIT_TERMINAL_PROMPT": "0"}
        self.script(self.bin / "curl", '''#!/bin/bash
echo download >> "$HOME/downloads"
cp "$TEST_ARCHIVE" "${@: -1}"
''')

    def credential_api(self):
        self.requests = []
        self.response = {"token": TOKEN, "username": "x-access-token"}
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append((self.path, body))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(owner.response).encode())

            def log_message(self, *_):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.env.update(BUILDKITE_AGENT_ENDPOINT=f"http://127.0.0.1:{server.server_port}/v3",
                        BUILDKITE_AGENT_ACCESS_TOKEN="test-agent-session", BUILDKITE_JOB_ID="job-123")

    def script(self, path, source):
        path.write_text(source)
        path.chmod(0o755)

    def hook(self, command="git-remote-entire --version"):
        return subprocess.run([
            "bash", "-c", 'source "$1/hooks/environment"; eval "$2"', "test", str(ROOT), command,
        ], env=self.env, cwd=self.home, text=True, capture_output=True, timeout=30)

    def test_missing_helper_is_installed_and_reused_without_job_credentials(self):
        result = self.hook('[[ -z ${ENTIRE_TOKEN+x} ]]; git-remote-entire --version')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("~~~ :package: Installing git-remote-entire", result.stdout.splitlines())
        self.assertIn(VERSION, result.stdout)
        self.assertEqual(list(self.installed.parent.iterdir()), [self.installed])
        installed = self.installed.stat()
        result = self.hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.installed.stat().st_ino, installed.st_ino)
        self.assertEqual((self.home / "downloads").read_text(), "download\n")
        self.assertFalse((self.home / ".gitconfig").exists())

    def test_supported_versions_are_not_replaced_or_downgraded(self):
        for version in (VERSION, "0.11.5-nightly.202610120640.a564a68c8",
                        "0.11.5", "0.11.10", "0.12.0", "1.0.0+build"):
            with self.subTest(version=version):
                self.script(self.bin / "git-remote-entire", f"#!/bin/sh\necho 'git-remote-entire {version}'\n")
                result = self.hook()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(version, result.stdout)
                self.assertFalse(self.installed.exists())
                self.assertFalse((self.home / "downloads").exists())

    def test_old_and_unidentifiable_versions_are_replaced_even_ahead_on_path(self):
        for version, status in (("0.11.4", 0), ("0.9.99", 0),
                                ("0.0.0+57de2c37992efdbcc0519bda2376ccf93f3020c2", 0),
                                ("unknown", 0), ("0.11.5", 1)):
            with self.subTest(version=version, status=status):
                self.installed.unlink(missing_ok=True)
                self.script(self.bin / "git-remote-entire", f"#!/bin/sh\necho 'git-remote-entire {version}'\nexit {status}\n")
                result = self.hook()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(VERSION, result.stdout)
                self.assertTrue(self.installed.is_file())

    def test_corrupt_download_preserves_existing_helper_and_cleans_staging(self):
        self.installed.parent.mkdir(parents=True)
        original = "#!/bin/sh\necho 'git-remote-entire 0.11.4'\n"
        self.script(self.installed, original)
        self.script(self.bin / "curl", '#!/bin/bash\nprintf corrupt > "${@: -1}"\n')
        result = self.hook()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum mismatch", result.stderr)
        self.assertEqual(self.installed.read_text(), original)
        self.assertEqual(list(self.installed.parent.iterdir()), [self.installed])

    def test_unsupported_install_platform_fails_before_downloading(self):
        (self.bin / "uname").unlink()
        for system, machine in (("Darwin", "arm64"), ("Linux", "riscv64")):
            with self.subTest(system=system, machine=machine):
                self.script(self.bin / "uname", f'#!/bin/sh\nif [ "$1" = -s ]; then echo {system}; else echo {machine}; fi\n')
                result = self.hook()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("automatic installation supports", result.stderr)
                self.assertFalse((self.home / "downloads").exists())

    def test_adapter_uses_agent_credentials_without_tokens_in_environment_or_files(self):
        self.credential_api()
        # Existing job config and HTTPS helper must survive. For Entire, reset
        # this helper or its password=fail response prevents our adapter running.
        self.env.update(GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_0="credential.helper",
                        GIT_CONFIG_VALUE_0="!buildkite-agent git-credentials-helper",
                        GIT_CONFIG_KEY_1="credential.useHttpPath", GIT_CONFIG_VALUE_1="true",
                        GIT_TRACE="1")
        for suffix in ("", ".git"):
            with self.subTest(suffix=suffix):
                self.env["BUILDKITE_REPO"] = URL + suffix
                for protocol in ("entire", "https"):
                    self.env["TEST_PROTOCOL"] = protocol
                    result = self.hook('''
[[ -z ${ENTIRE_TOKEN+x} ]]
credentials=$(printf 'protocol=%s\nhost=region.entire.io\npath=et/project/repository%s\n\n' "$TEST_PROTOCOL" "${BUILDKITE_REPO#''' + URL + '''}" | git credential fill)
printf '%s' "$credentials" | sha256sum
unset credentials
export -p > "$HOME/after-hook"
''')
                    self.assertEqual(result.returncode, 0, result.stderr)
                    expected = (f"protocol={protocol}\nhost=region.entire.io\n"
                                f"path=et/project/repository{suffix}\nusername=x-access-token\npassword={TOKEN}")
                    self.assertIn(hashlib.sha256(expected.encode()).hexdigest(), result.stdout)
                    self.assertNotIn(TOKEN, result.stdout + result.stderr)
                    self.assertNotIn(TOKEN, (self.home / "after-hook").read_text())
                    self.assertEqual(self.requests[-1], ("/v3/jobs/job-123/repository_access_token",
                                                       {"repo_url": f"https://region.entire.io/et/project/repository{suffix}"}))
        self.assertEqual(len(self.requests), 4)
        self.assertFalse((self.home / ".gitconfig").exists())

    def test_adapter_is_scoped_and_not_persisted_for_other_jobs(self):
        self.credential_api()
        self.env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="credential.helper",
                        GIT_CONFIG_VALUE_0="!echo username=unrelated; echo password=unrelated")
        for path in ("et/project/other", "et/project/repository/child"):
            result = self.hook(f"printf 'protocol=entire\\nhost=region.entire.io\\npath={path}\\n\\n' | git credential fill")
            if path.endswith("/child"):
                # Git URL scopes also match descendants; the adapter must reject
                # those explicitly rather than forwarding a broader request.
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("password=", result.stdout)
                continue
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("password=unrelated", result.stdout)
        self.assertEqual(self.requests, [])
        result = subprocess.run(["git", "config", "--get-all", "credential.helper"],
                                env=self.env, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), self.env["GIT_CONFIG_VALUE_0"])

    def test_adapter_passes_agent_errors_to_stderr(self):
        self.credential_api()
        self.response = {"token": "", "message": TOKEN}
        self.env.update(GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_0="credential.helper",
                        GIT_CONFIG_VALUE_0="!buildkite-agent git-credentials-helper",
                        GIT_CONFIG_KEY_1="credential.helper",
                        GIT_CONFIG_VALUE_1="!echo username=wrong; echo password=wrong")
        result = self.hook('printf "url=%s\\n\\n" "$BUILDKITE_REPO" | git credential fill')
        self.assertNotEqual(result.returncode, 0)
        diagnostic = "repository credential response contained an empty token"
        self.assertIn(diagnostic, result.stderr)
        self.assertNotIn(diagnostic, result.stdout)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)

    def test_native_operator_chain_preserves_protocol_order_and_resets(self):
        self.script(self.bin / "git-credential-operator", '''#!/bin/bash
[[ $1 == "space ' quote" && $2 == get ]] || exit 1
request=$(cat)
[[ $request == *protocol=entire* ]] || exit 1
[[ $request == *username=operator* ]] || exit 1
printf 'password=operator-secret\n'
''')
        config = self.home / ".gitconfig"
        config.write_text('''[credential]
    helper = !echo username=wrong; echo password=wrong
[credential "entire://region.entire.io/et/project"]
    helper =
    helper = !exit 1
    helper = !echo username=operator
[credential "https://region.entire.io/et/project/repository"]
    helper = !echo quit=true
''')
        self.env.update(GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_0=f"credential.{URL}.helper",
                        GIT_CONFIG_KEY_1="credential.helper", GIT_CONFIG_VALUE_1="!echo quit=true")
        for helper in ('operator "space \' quote"',
                       f'{self.bin}/git-credential-operator "space \' quote"',
                       '!f() {\ngit credential-operator "space \' quote" "$@"\n}; f'):
            with self.subTest(helper=helper):
                self.env["GIT_CONFIG_VALUE_0"] = helper
                before = subprocess.run(["git", "credential", "fill"], input=f"url={URL}\n\n",
                                        env=self.env, cwd=self.home, text=True, capture_output=True)
                self.assertEqual(before.returncode, 0, before.stderr)
                self.assertIn("password=operator-secret", before.stdout)
                result = self.hook('printf "url=%s\\n\\n" "$BUILDKITE_REPO" | git credential fill')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(before.stdout, result.stdout)

    def test_agent_generated_quoted_command_and_operator_chain(self):
        self.credential_api()
        directory = self.home / "agent's bin"
        directory.mkdir()
        agent = directory / "buildkite-agent"
        shutil.copyfile(self.agent, agent)
        agent.chmod(0o755)
        (self.bin / "buildkite-agent").unlink()
        (self.bin / "buildkite-agent").symlink_to(agent)
        quoted = "'" + str(agent).replace("'", "'\\''") + "'"
        self.env.update(GIT_CONFIG_COUNT="3", GIT_CONFIG_KEY_0="credential.helper",
                        GIT_CONFIG_VALUE_0="!echo username=partial",
                        GIT_CONFIG_KEY_1="credential.helper",
                        GIT_CONFIG_VALUE_1=f"!{quoted} git-credentials-helper",
                        GIT_CONFIG_KEY_2="credential.helper", GIT_CONFIG_VALUE_2="!echo quit=true")
        result = self.hook('printf "url=%s\\n\\n" "$BUILDKITE_REPO" | git credential fill')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"username=x-access-token\npassword={TOKEN}", result.stdout)
        self.assertEqual(self.requests, [("/v3/jobs/job-123/repository_access_token",
                                         {"repo_url": "https://region.entire.io/et/project/repository"})])

    def test_exhausted_or_refused_chain_cannot_prompt_or_fall_back(self):
        self.script(self.bin / "askpass", '#!/bin/bash\necho invoked > "$HOME/prompted"\necho wrong\n')
        self.env.update(GIT_ASKPASS=str(self.bin / "askpass"), GIT_TERMINAL_PROMPT="1")
        for helpers in ([], ["!echo username=partial"], ["!exit 1"],
                        ["!echo quit=true", "!echo username=wrong; echo password=wrong"]):
            with self.subTest(helpers=helpers):
                self.env["GIT_CONFIG_COUNT"] = str(len(helpers))
                for index, helper in enumerate(helpers):
                    self.env[f"GIT_CONFIG_KEY_{index}"] = "credential.helper"
                    self.env[f"GIT_CONFIG_VALUE_{index}"] = helper
                result = self.hook('printf "url=%s\\n\\n" "$BUILDKITE_REPO" | git credential fill')
                self.assertEqual(result.returncode, 128, result.stderr)
                self.assertNotIn("password=", result.stdout)
                self.assertFalse((self.home / "prompted").exists())

    def test_pinned_remote_helper_requests_native_credentials(self):
        # Install the real pinned binary, then run it without the adapter.
        self.assertEqual(self.hook().returncode, 0)
        self.env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="credential.helper",
                        GIT_CONFIG_VALUE_0='!cat > "$HOME/native-request"; echo quit=true')
        result = subprocess.run([str(self.installed), "origin", URL], input="capabilities\n",
                                env=self.env, cwd=self.home, text=True, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.home / "native-request").read_text(),
                         "protocol=entire\nhost=region.entire.io\npath=et/project/repository\n")

    def test_installed_helper_uses_adapter_and_fails_closed_without_leaking_errors(self):
        self.credential_api()
        self.response = {"token": "", "message": TOKEN}
        self.env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="credential.helper",
                        GIT_CONFIG_VALUE_0="!buildkite-agent git-credentials-helper")
        result = self.hook('git ls-remote "$BUILDKITE_REPO"')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("git credential lookup failed", result.stderr)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        self.assertEqual(self.requests, [("/v3/jobs/job-123/repository_access_token",
                                         {"repo_url": "https://region.entire.io/et/project/repository"})])

    def test_invalid_repository_cannot_broaden_credential_scope(self):
        for url in ("", "https://region.entire.io/et/p/r", "entire://*.entire.io/et/p/r",
                    "entire://token@region.entire.io/et/p/r", URL + "\nhost=other.entire.io"):
            with self.subTest(url=url):
                self.env["BUILDKITE_REPO"] = url
                result = self.hook()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("must be a native", result.stderr)
                self.assertFalse((self.home / "downloads").exists())


if __name__ == "__main__":
    unittest.main()
