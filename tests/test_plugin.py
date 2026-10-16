"""Exercise installation and environment-token handoff with real binaries."""

import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import ssl
import subprocess
import tarfile
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "4b8cdfaf0d15e236835c3b7c85d8803b112574bc"
VERSION = f"0.0.0+{COMMIT}"
URL = "entire://region.entire.io/et/project/repository"
SETTINGS = "https://buildkite.com/organizations/{}/repository-providers"
OPT_IN = '"Allow self-hosted agents to use checkout credentials"'


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
        for name in ("bash", "git", "python3", "sort", "mkdir", "cp", "uname", "mktemp", "sed", "cat",
                     "sha256sum", "tar", "gzip", "rm", "mv"):
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
        self.response = {"token": secrets.token_hex(20), "username": "x-access-token"}
        self.response_status = 200
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append((self.path, body))
                self.send_response(owner.response_status)
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
                        BUILDKITE_AGENT_ACCESS_TOKEN="test-agent-session", BUILDKITE_JOB_ID="job-123",
                        BUILDKITE_COMPUTE_TYPE="hosted")

    def script(self, path, source):
        path.write_text(source)
        path.chmod(0o755)

    def hook(self, command="git-remote-entire --version", trace=False):
        return subprocess.run([
            "bash", *(["-x"] if trace else []), "-c",
            'source "$1/hooks/environment"; eval "$2"', "test", str(ROOT), command,
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
        for version in (VERSION, "0.11.5", "0.11.10", "0.12.0", "1.0.0+build"):
            with self.subTest(version=version):
                self.script(self.bin / "git-remote-entire", f"#!/bin/sh\necho 'git-remote-entire {version}'\n")
                result = self.hook()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(version, result.stdout)
                self.assertFalse(self.installed.exists())
                self.assertFalse((self.home / "downloads").exists())

    def test_old_and_unidentifiable_versions_are_replaced_even_ahead_on_path(self):
        for version, status in (("0.11.4", 0), ("0.9.99", 0),
                                ("0.11.5-nightly.202610120640.a564a68c8", 0),
                                ("0.0.0+a564a68c802d50a0f4cff333da6ee13d59be027d", 0),
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

    def test_token_is_exported_once_without_config_changes_or_leaks(self):
        self.credential_api()
        token = self.response["token"]
        self.env.update(ENTIRE_TOKEN="", ENTIRE_GIT_NO_LOGIN_FALLBACK="true",
                        GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="credential.helper",
                        GIT_CONFIG_VALUE_0="!echo quit=true", GIT_TRACE="1")
        before = subprocess.run(["git", "config", "--null", "--list"], env=self.env,
                                cwd=self.home, capture_output=True, check=True)
        for compute, suffix in (("hosted", ""), ("self-hosted", ".git"), ("unknown", ""), (None, ".git")):
            self.env.pop("BUILDKITE_COMPUTE_TYPE", None)
            if compute is not None:
                self.env["BUILDKITE_COMPUTE_TYPE"] = compute
            for trace in (False, True):
                with self.subTest(compute=compute, suffix=suffix, trace=trace):
                    self.env["BUILDKITE_REPO"] = URL + suffix
                    result = self.hook('''
python3 -c 'import hashlib, os; token = os.environ["ENTIRE_TOKEN"]; assert [k for k, v in os.environ.items() if token in v] == ["ENTIRE_TOKEN"]; print(hashlib.sha256(token.encode()).hexdigest())'
[[ $ENTIRE_GIT_NO_LOGIN_FALLBACK == true ]]
git config --null --list | sha256sum
case $- in *x*) echo tracing=on ;; *) echo tracing=off ;; esac
''', trace=trace)
                    self.assertEqual(result.returncode, 0)
                    self.assertIn(hashlib.sha256(token.encode()).hexdigest(), result.stdout)
                    self.assertIn(hashlib.sha256(before.stdout).hexdigest(), result.stdout)
                    self.assertIn(f"tracing={'on' if trace else 'off'}", result.stdout)
                    self.assertFalse(token in result.stdout + result.stderr, "Token leaked to output")
                    self.assertNotIn("repository-providers", result.stdout + result.stderr)
                    self.assertEqual(self.requests[-1], ("/v3/jobs/job-123/repository_access_token",
                                                       {"repo_url": f"https://region.entire.io/et/project/repository{suffix}"}))
        self.assertEqual(len(self.requests), 8)
        for path in self.home.rglob("*"):
            if path.is_file() and not path.is_symlink():
                self.assertFalse(token.encode() in path.read_bytes(), "Token persisted to a file")

    def test_credential_errors_continue_without_token_or_leaks(self):
        self.credential_api()
        secret = secrets.token_hex(20)
        self.env.update(ENTIRE_TOKEN="", ENTIRE_GIT_NO_LOGIN_FALLBACK="false")
        for compute, org, link in (("hosted", "acme-inc", "acme-inc"), ("self-hosted", None, "~"),
                                   ("self-hosted", "../evil", "~")):
            self.env["BUILDKITE_COMPUTE_TYPE"] = compute
            self.env.pop("BUILDKITE_ORGANIZATION_SLUG", None)
            if org is not None:
                self.env["BUILDKITE_ORGANIZATION_SLUG"] = org
            for status, token in ((200, ""), (200, " \t"), (200, secret + " invalid"),
                                  (200, secret + "\npassword=second"), (403, secret)):
                with self.subTest(compute=compute, status=status, empty=not token):
                    self.response_status = status
                    self.response = {"token": token, "message": secret}
                    result = self.hook('''
[[ -z ${ENTIRE_TOKEN+x} ]]
[[ $ENTIRE_GIT_NO_LOGIN_FALLBACK == false ]]
case $- in *x*) echo continued ;; *) exit 1 ;; esac
''', trace=True)
                    self.assertEqual(result.returncode, 0)
                    self.assertIn("continued", result.stdout)
                    self.assertIn("~~~ :warning: Entire: Buildkite did not issue checkout credentials\n", result.stderr)
                    self.assertIn(OPT_IN, result.stderr)
                    self.assertIn(f"Entire: {SETTINGS.format(link)}\n", result.stderr)
                    self.assertIn("Continuing with a saved Entire login", result.stderr)
                    self.assertFalse(secret in result.stdout + result.stderr, "Credential leaked to output")
        self.assertEqual(len(self.requests), 15)

    def test_missing_credential_helper_does_not_mask_later_failures(self):
        (self.bin / "buildkite-agent").unlink()
        result = self.hook('[[ -z ${ENTIRE_TOKEN+x} ]]; echo continued; exit 42', trace=True)
        self.assertEqual(result.returncode, 42)
        self.assertIn("continued", result.stdout)

    def test_pinned_helper_uses_environment_bearer_and_server_repository_authorization(self):
        self.credential_api()
        cert, key = self.home / "cert.pem", self.home / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        git_requests = []
        user_agents = []
        oid = b"1" * 40
        lines = [b"# service=git-upload-pack\n", None,
                 oid + b" HEAD\0symref=HEAD:refs/heads/main object-format=sha1\n",
                 oid + b" refs/heads/main\n", None]
        advertisement = b"".join(b"0000" if line is None else f"{len(line) + 4:04x}".encode() + line
                                 for line in lines)

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                user_agents.append(self.headers.get("User-Agent"))
                if self.path == "/.well-known/entire-cluster.json":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"core_urls": [origin]}).encode())
                    return
                git_requests.append((self.path, self.headers.get("Authorization")))
                allowed = (self.path == "/et/project/repository/info/refs?service=git-upload-pack"
                           and self.headers.get("Authorization") in {f"Bearer {token}", f"Bearer {saved_token}"})
                self.send_response(200 if allowed else 403)
                self.send_header("Content-Type", "application/x-git-upload-pack-advertisement")
                self.end_headers()
                self.wfile.write(advertisement if allowed else b"denied")

            def log_message(self, *_):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        origin = f"https://127.0.0.1:{server.server_port}"
        # Synthetic JWT: the client reads aud; this fixture checks the bearer,
        # not its signature. Live Entire owns token signature/scope validation.
        token = ".".join(base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
                         for value in ({"alg": "HS256"}, {"aud": origin})) + ".c2lnbmF0dXJl"
        saved_token = ".".join(base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
                               for value in ({"alg": "HS256"}, {"iss": origin, "handle": "fixture-user",
                                                                       "exp": 4102444800})) + ".c2lnbmF0dXJl"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.response["token"] = token
        self.env.update(BUILDKITE_REPO=origin.replace("https://", "entire://") + "/et/project/repository",
                        SSL_CERT_FILE=str(cert), GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="credential.helper",
                        GIT_CONFIG_VALUE_0='!echo used > "$HOME/git-used"; echo quit=true')
        for user_agent, expected in ((None, f"git-remote-entire/{VERSION}"),
                                     ("buildkite-agent/4.3.0 stable-pin-test", "buildkite-agent/4.3.0 stable-pin-test"),
                                     ("", None)):
            with self.subTest(user_agent=user_agent):
                self.env.pop("GIT_HTTP_USER_AGENT", None)
                if user_agent is not None:
                    self.env["GIT_HTTP_USER_AGENT"] = user_agent
                self.requests.clear()
                git_requests.clear()
                user_agents.clear()
                result = self.hook('''
git -c protocol.version=0 ls-remote "$BUILDKITE_REPO"
if git -c protocol.version=0 ls-remote "${BUILDKITE_REPO%/*}/other"; then exit 1; fi
''')
                self.assertEqual(result.returncode, 0)
                self.assertIn("1" * 40 + "\trefs/heads/main", result.stdout)
                self.assertFalse((self.home / "git-used").exists())
                self.assertFalse(token in result.stdout + result.stderr, "Bearer leaked to output")
                self.assertEqual(self.requests, [("/v3/jobs/job-123/repository_access_token",
                                                 {"repo_url": origin + "/et/project/repository"})])
                self.assertTrue(any("/repository/info/refs" in path for path, _ in git_requests))
                self.assertTrue(any("/other/info/refs" in path for path, _ in git_requests))
                self.assertTrue(all(auth == f"Bearer {token}" for _, auth in git_requests), "Wrong bearer")
                self.assertTrue(user_agents)
                self.assertEqual(set(user_agents), {expected})

        # A usable saved identity must not bypass an explicit login opt-out.
        config = self.home / "entire-config"
        config.mkdir()
        (config / "contexts.json").write_text(json.dumps({
            "current_context": "fixture", "contexts": [{"name": "fixture", "core_url": origin,
            "handle": "fixture-user", "keychain_service": f"entire-core:{origin}"}]}))
        store = self.home / "tokens.json"
        store.write_text(json.dumps({f"entire-core:{origin}": {"fixture-user": saved_token + "|4102444800"},
                                    f"entire-core:{origin}:refresh": {"fixture-user": "fixture-refresh"}}))
        self.env.update(BUILDKITE_COMPUTE_TYPE="self-hosted", ENTIRE_CONFIG_DIR=str(config),
                        ENTIRE_TOKEN_STORE="file", ENTIRE_TOKEN_STORE_PATH=str(store),
                        XDG_CACHE_HOME=str(self.home / "cache"))
        self.env.pop("GIT_HTTP_USER_AGENT", None)
        # Issuance is unavailable; the existing login policy still applies.
        self.response_status = 403
        for fallback in ("true", "1", "T", "TRUE", "True", "t", "", "typo", " true"):
            with self.subTest(fallback=fallback):
                self.requests.clear()
                self.env["ENTIRE_GIT_NO_LOGIN_FALLBACK"] = fallback
                git_requests.clear()
                user_agents.clear()
                result = self.hook('git -c protocol.version=0 ls-remote "$BUILDKITE_REPO"', trace=True)
                self.assertNotEqual(result.returncode, 0)
                if fallback in ("", "typo", " true"):
                    self.assertIn("must be a boolean", result.stderr)
                else:
                    self.assertIn("saved-login fallback is disabled", result.stderr)
                    self.assertIn(OPT_IN, result.stderr)
                    self.assertIn(SETTINGS.format("~"), result.stderr)
                    self.assertNotIn("Continuing", result.stderr)
                self.assertEqual(git_requests, [], "Used saved identity despite login opt-out")
                self.assertEqual(user_agents, [], "Contacted Entire despite login opt-out")
                self.assertEqual(len(self.requests), 1)

        # Prove the saved identity works when login fallback is permitted.
        for fallback in (None, "false", "0", "f", "F", "FALSE", "False"):
            with self.subTest(fallback=fallback):
                self.requests.clear()
                self.env.pop("ENTIRE_GIT_NO_LOGIN_FALLBACK", None)
                if fallback is not None:
                    self.env["ENTIRE_GIT_NO_LOGIN_FALLBACK"] = fallback
                git_requests.clear()
                result = self.hook('git -c protocol.version=0 ls-remote "$BUILDKITE_REPO"')
                self.assertEqual(result.returncode, 0)
                self.assertIn("1" * 40 + "\trefs/heads/main", result.stdout)
                self.assertTrue(git_requests)
                self.assertTrue(all(auth == f"Bearer {saved_token}" for _, auth in git_requests))
                self.assertEqual(len(self.requests), 1)

        # A supplied token takes precedence; an empty one needs acquisition.
        self.env["ENTIRE_GIT_NO_LOGIN_FALLBACK"] = "typo"
        for supplied in (token, ""):
            with self.subTest(token_nonempty=bool(supplied)):
                self.requests.clear()
                self.env["ENTIRE_TOKEN"] = supplied
                git_requests.clear()
                result = self.hook('git -c protocol.version=0 ls-remote "$BUILDKITE_REPO"', trace=True)
                if supplied:
                    self.assertEqual(result.returncode, 0)
                    self.assertTrue(git_requests)
                    self.assertTrue(all(auth == f"Bearer {token}" for _, auth in git_requests))
                    self.assertFalse(token in result.stdout + result.stderr, "Bearer leaked to output")
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(git_requests, [], "Empty token fell back to saved identity")
                self.assertEqual(len(self.requests), 0 if supplied else 1)

    def test_existing_token_preserves_operator_auth_without_request_or_leaks(self):
        self.credential_api()
        self.env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="credential.helper",
                        GIT_CONFIG_VALUE_0="!echo quit=true")
        before = subprocess.run(["git", "config", "--null", "--list"], env=self.env,
                                cwd=self.home, capture_output=True, check=True)
        token = secrets.token_hex(20)
        for compute, fallback in (("hosted", "false"), ("self-hosted", "true"),
                                  (None, None), ("unknown", "false")):
            with self.subTest(compute=compute):
                for name, value in (("BUILDKITE_COMPUTE_TYPE", compute), ("ENTIRE_TOKEN", token),
                                    ("ENTIRE_GIT_NO_LOGIN_FALLBACK", fallback)):
                    self.env.pop(name, None)
                    if value is not None:
                        self.env[name] = value
                result = self.hook('''
git-remote-entire --version
python3 -c 'import hashlib, os; token = os.environ.get("ENTIRE_TOKEN"); print("unset" if token is None else hashlib.sha256(token.encode()).hexdigest())'
printf 'fallback=%s\\n' "${ENTIRE_GIT_NO_LOGIN_FALLBACK-unset}"
git config --null --list | sha256sum
''', trace=True)
                self.assertEqual(result.returncode, 0)
                self.assertIn(VERSION, result.stdout)
                self.assertIn(hashlib.sha256(token.encode()).hexdigest(), result.stdout)
                self.assertIn(f"fallback={fallback if fallback is not None else 'unset'}\n", result.stdout)
                self.assertIn(hashlib.sha256(before.stdout).hexdigest(), result.stdout)
                self.assertFalse(token in result.stdout + result.stderr, "Token leaked to output")
                self.assertNotIn("repository-providers", result.stdout + result.stderr)
        self.assertEqual(self.requests, [])

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
