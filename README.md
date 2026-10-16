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

## Authentication

Buildkite issues short-lived, read-only Entire checkout credentials to command
jobs. The plugin requests them and sets `ENTIRE_TOKEN` for the job, so no Entire
login is needed. If you set a non-empty `ENTIRE_TOKEN`, the plugin uses it and
does not request credentials.

- **Hosted agents:** no setup is needed.
- **Self-hosted agents:** use Agent v4.3.0 or later, and have a Buildkite
  administrator enable **Allow self-hosted agents to use checkout credentials**
  in the Entire provider settings under
  [Repository Providers](https://buildkite.com/organizations/~/repository-providers).
  Alternatively, export your own `ENTIRE_TOKEN` in an
  [agent environment hook](https://buildkite.com/docs/agent/v3/hooks#job-lifecycle-hooks).

If Buildkite does not issue credentials, the plugin shows a warning with a link
to these settings and continues without a token. Entire then uses a saved
Entire login on the agent, if one exists. Set `ENTIRE_GIT_NO_LOGIN_FALLBACK=true`
to fail the job instead of using a saved login. Entire v0.11.5 no longer reads
Git credentials, and the plugin does not change Git credentials or saved-login
settings.

We recommend [installing the Entire CLI](https://docs.entire.io/installation)
for self-hosted agents, including `git-remote-entire` on `PATH`.

Do not print `ENTIRE_TOKEN` or dump the job's environment. Acquired credentials are
not refreshed and can expire during long jobs.

## Runtime requirements

Automatic installation supports Linux amd64 and arm64, with Bash, curl, Git,
GNU coreutils, gzip, sed, and tar.

## License

[MIT](LICENSE)
