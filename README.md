# Entire Buildkite Plugin

Check out [Entire](https://entire.io) repositories with Buildkite.

Set your pipeline's repository to its `entire://` URL and add the plugin:

```yaml
steps:
  - command: ./test.sh
    plugins:
    - entire
```

Installs or upgrades the Git remote helper when needed and reuses it across jobs.
There are no plugin options.

The plugin preserves a non-empty `ENTIRE_TOKEN`. Otherwise, it asks Buildkite
for Entire checkout credentials on any agent type. If Buildkite issues them, the
plugin sets `ENTIRE_TOKEN` for the job; no Entire login is needed.

If Buildkite does not issue credentials, the plugin shows the agent's error,
which gives Buildkite's reason, and continues without a token. Checkout can
still authenticate with a saved Entire login or other agent configuration.
Self-hosted issuance requires **Allow self-hosted agents to use checkout
credentials** in the Entire repository provider settings in Buildkite, not a
plugin option. You can also export your own `ENTIRE_TOKEN` in an
[agent environment hook](https://buildkite.com/docs/agent/v3/hooks#job-lifecycle-hooks).
We recommend [installing the Entire CLI](https://docs.entire.io/installation)
for self-hosted agents, including `git-remote-entire` on `PATH`. The plugin does
not change Git credentials or saved-login and fallback settings on any agent.

If authentication then fails, the plugin explains what credentials the job had
and how to fix it: turning on the provider setting, a token Entire rejected, or
a missing login. It does this by running `git-remote-entire` through a wrapper
for the job, so it covers checkout and later Git commands on `entire://`
remotes. It explains the first failure only, and recognises the errors of the
pinned helper; other failures get a short note.

Entire v0.11.5 no longer reads Git credentials. If no token is available and
`ENTIRE_GIT_NO_LOGIN_FALLBACK=true`, the plugin fails rather than use a saved
Entire login. Supply `ENTIRE_TOKEN` for jobs that disable saved-login fallback.

Do not print `ENTIRE_TOKEN` or dump the job's environment. Acquired credentials are
not refreshed and can expire during long jobs.

## Runtime requirements

Automatic installation supports Linux amd64 and arm64, with Bash, curl, Git,
GNU coreutils, gzip, sed, and tar.

## License

[MIT](LICENSE)
