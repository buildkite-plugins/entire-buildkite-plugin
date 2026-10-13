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

On hosted agents (`BUILDKITE_COMPUTE_TYPE=hosted`), Buildkite's Git credential
integration handles authentication. The plugin filters requests to the exact
repository, translates the credential protocol to HTTPS for older agents, and
disables saved Entire login fallback. Agent failures stop authentication rather
than falling through to other credentials. Requires Buildkite's Entire checkout
integration and Agent 4.3.0 or later; no Entire login or token configuration is
needed.

On self-hosted agents, or when compute type is absent or unrecognized, the plugin
only installs or reuses the remote helper. It leaves Git credential configuration
and `ENTIRE_GIT_NO_LOGIN_FALLBACK` unchanged. Operators retain control of
authentication.

Automatic installation supports Linux amd64 and arm64, with Bash, curl, Git,
GNU coreutils, sed, and tar.

## License

[MIT](LICENSE)
