"""Exercise the installation hook and the real helper's native credential lookup."""

import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a564a68c802d50a0f4cff333da6ee13d59be027d"
VERSION = f"0.0.0+{COMMIT}"


class PluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.download = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.download.cleanup)
        cls.archive = Path(os.environ.get("ENTIRE_TEST_ARCHIVE", f"{cls.download.name}/helper.tar.gz"))
        if not cls.archive.exists():
            arch = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
            subprocess.run(["curl", "-qfsSL", "--proto", "=https", "--proto-redir", "=https",
                            f"https://entire-public-release-bucket-7f3e2a01c9b48d56.s3.us-east-2.amazonaws.com/commit/{COMMIT}/git-remote-entire_linux_{arch}.tar.gz",
                            "-o", str(cls.archive)], check=True, timeout=180)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.installed = self.home / ".local/bin/git-remote-entire"
        # Do not pick up a host helper, Git configuration, or credentials.
        for name in ("bash", "git", "sort", "mkdir", "cp", "uname", "mktemp",
                     "sha256sum", "tar", "gzip", "rm", "mv"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.env = {"HOME": str(self.home), "PATH": str(self.bin),
                    "GIT_CONFIG_NOSYSTEM": "1", "TEST_ARCHIVE": str(self.archive)}
        self.script(self.bin / "curl", '''#!/bin/bash
echo download >> "$HOME/downloads"
cp "$TEST_ARCHIVE" "${@: -1}"
''')

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

    def test_installed_helper_uses_native_git_credentials_and_refuses_login_fallback(self):
        self.script(self.bin / "git-credential-test", '''#!/bin/bash
while IFS= read -r line && [[ -n $line ]]; do
  printf '%s\n' "$line" >> "$HOME/credential-request"
done
printf 'quit=true\n\n'
''')
        (self.home / ".gitconfig").write_text("[credential]\n  helper = test\n  useHttpPath = true\n")
        result = self.hook('git ls-remote entire://region.entire.io/et/project/repository')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("git credential lookup failed", result.stderr)
        self.assertEqual((self.home / "credential-request").read_text(),
                         "protocol=entire\nhost=region.entire.io\npath=et/project/repository\n")
        # A silent helper failure must not substitute a saved personal login.
        self.script(self.bin / "git-credential-test", "#!/bin/sh\nexit 1\n")
        result = self.hook('git ls-remote entire://region.entire.io/et/project/repository')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("saved-login fallback is disabled", result.stderr)


if __name__ == "__main__":
    unittest.main()
