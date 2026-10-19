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

The plugin preserves a non-empty `ENTIRE_TOKEN`. Otherwise, it tries Buildkite's
Entire checkout integration on any agent type.
If credentials are available, it sets `ENTIRE_TOKEN` for the job; no Entire login
is needed. If acquisition fails or returns unusable credentials, the plugin
continues without a token, leaving saved-login and fallback settings unchanged.
It prints guidance for checking the repository provider settings if checkout
fails. It does not intercept checkout or diagnose the cause of a failure.

Self-hosted token issuance requires provider opt-in in Buildkite, not a plugin
option. You can also export your own `ENTIRE_TOKEN` in an
[agent environment hook](https://buildkite.com/docs/agent/v3/hooks#job-lifecycle-hooks).
We recommend [installing the Entire CLI](https://docs.entire.io/installation)
for self-hosted agents, including `git-remote-entire` on `PATH`. The plugin does
not change Git credentials or saved-login and fallback settings on any agent.

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
