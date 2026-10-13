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

On hosted agents, authentication is automatic with Buildkite's Entire checkout
integration and Agent 4.3.0 or later. No Entire login is needed. The plugin sets
`ENTIRE_TOKEN` for the job, replacing any existing value. The job fails if
credentials cannot be acquired.

On self-hosted agents, export your own `ENTIRE_TOKEN` in an
[agent environment hook](https://buildkite.com/docs/agent/v3/hooks#job-lifecycle-hooks).
We recommend [installing the Entire CLI](https://docs.entire.io/installation)
for the agent user, including `git-remote-entire` on `PATH`. On all non-hosted
agents, the plugin preserves your Git credentials, `ENTIRE_TOKEN`, and login
fallback settings.

Do not print `ENTIRE_TOKEN` or dump the job's environment. Hosted credentials are
not refreshed and can expire during long jobs.

Automatic installation supports Linux amd64 and arm64, with Bash, curl, Git,
GNU coreutils, sed, and tar.

## License

[MIT](LICENSE)
