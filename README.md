# Entire Buildkite Plugin

Check out [Entire](https://entire.io) repositories with Buildkite.

```yaml
steps:
  - command: ./test.sh
    plugins:
    - entire
```

Installs or upgrades the Git remote helper when needed and reuses it across jobs.
There are no plugin options.

On hosted agents (`BUILDKITE_COMPUTE_TYPE=hosted`), the environment hook acquires
the job's selected-repository credential once and exports it as `ENTIRE_TOKEN`,
replacing any existing hosted value. Requires Buildkite's Entire checkout
integration and Agent 4.3.0 or later; no Entire login is needed.

The plugin calls the agent's internal `git-credentials-helper get` command only
to acquire the credential. It does not install a Git credential helper or change
Git configuration. The pinned Entire helper [consumes `ENTIRE_TOKEN` as a JWT
bearer](https://github.com/entireio/cli/blob/a564a68c802d50a0f4cff333da6ee13d59be027d/cmd/git-remote-entire/main.go#L368-L392),
bypassing Git credentials and saved login. Empty credentials or acquisition
errors fail the hook; diagnostics are deliberately generic to avoid logging
credential material.

The token is available to job subprocesses: do not print it or dump the job's
environment. It is not refreshed and can expire during long jobs. Buildkite
authorizes the selected repository at acquisition, but the environment bearer
can be sent to other repositories in the trusted cluster. Entire's server must
enforce its repository scope; the plugin does not filter later requests.

On self-hosted agents, or when compute type is absent or unrecognized, the plugin
only installs or reuses the remote helper. It leaves Git credential configuration
and existing `ENTIRE_TOKEN` and `ENTIRE_GIT_NO_LOGIN_FALLBACK` values unchanged.
Operators retain control of authentication.

Automatic installation supports Linux amd64 and arm64, with Bash, curl, Git,
GNU coreutils, sed, and tar.

## License

[MIT](LICENSE)
