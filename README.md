# Entire Buildkite Plugin

Check out [Entire](https://entire.io) repositories with Buildkite.

```yaml
steps:
  - command: ./test.sh
    plugins:
    - entire
```

Installs or upgrades the Git remote helper when needed and reuses it across jobs.
Uses the Git credential helpers configured before the environment hook, preserving
their order, empty resets, and `entire://` URL scopes. There are no plugin options.

On hosted agents, requires Buildkite's Entire checkout integration and Agent 4.3.0
or later. On self-hosted agents, configure a Git credential helper for the Entire
repository before this hook runs. No Entire login is needed.

Operator helpers receive the native `entire` protocol. Only a detected Buildkite
agent helper receives the HTTPS alias required by older agents. Detection supports
`!buildkite-agent git-credentials-helper` and the agent-generated quoted command
using the agent on PATH or its resolved path; custom wrappers must handle the
native protocol themselves.

Resolved-path detection needs `readlink -f`. On a provisioned system without it
(such as macOS without GNU coreutils), a helper quoting the resolved agent path
will not be recognized if PATH points to a symlink. Supply GNU `readlink` on PATH
or configure the helper with the quoted PATH executable instead.

The filter rejects descendant repository paths and leaves unrelated repositories
unchanged. A refused or exhausted helper chain fails without prompting or falling
back to a saved Entire login. Agent errors stop the chain. No retrieved tokens or
Git configuration are written to disk.

Automatic installation supports Linux amd64 and arm64, with Bash, curl, Git,
GNU coreutils, sed, and tar.

## License

[MIT](LICENSE)
