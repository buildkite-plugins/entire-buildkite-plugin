# Entire Buildkite Plugin

Install the native [Entire Git remote helper](https://github.com/entireio/cli)
and authenticate checkout with Buildkite credentials.

```yaml
plugins:
  - sj26/entire
```

Uses the native `entire://` URL in `BUILDKITE_REPO` and the agent's normal
checkout. Add the plugin explicitly; no plugin configuration or Entire login is
needed.

The environment hook reuses an existing `git-remote-entire`. If missing, it
downloads the same helper-only, commit-pinned S3 build as
[Entire's plugin](https://github.com/entireio/entire-core-auth-buildkite-plugin/blob/cc7050e0c8b9d0feae2cbebddf220890252d1c5c/hooks/environment):
[CLI commit 57de2c3](https://github.com/entireio/cli/commit/57de2c37992efdbcc0519bda2376ccf93f3020c2).
The plugin verifies its checksum, installs into `~/.local/bin`, adds that
directory to PATH, and leaves it installed. Automatic installation supports
Linux amd64 and arm64; provision the helper yourself on other platforms. It does
not install the full CLI or use Entire's OIDC exchange.

The hook calls `buildkite-agent git-credentials-helper get` directly, before
checkout, and exports its password as `ENTIRE_TOKEN`. It does not depend on Git
credential configuration being installed. The agent helper requires HTTPS, so
the lookup uses the native URL's exact host and path with only the scheme
changed; `BUILDKITE_REPO` stays unchanged. This lookup alias is **not** the
repository's HTTPS clone URL: no `.git` suffix is added.

End-to-end use requires the Entire issuer compatibility in
[Buildkite PR #35448](https://github.com/buildkite/buildkite/pull/35448). The issuer
must match that alias against the selected repository's current listing entry
before issuing credentials. Picker changes alone do not provide authentication.

`ENTIRE_TOKEN` is available to later job commands and the agent's hook environment
snapshots. The token is installation-wide and expires after at most 45 minutes.
It is requested once in the environment hook, not refreshed; later Git operations
fail after it expires. No remote wrapper or CLI login is used.
