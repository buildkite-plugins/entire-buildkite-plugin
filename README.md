# Entire Buildkite Plugin

Check out [Entire](https://entire.io) repositories with Buildkite.

```yaml
steps:
  - command: ./test.sh
    plugins: [entire]
```

Installs or upgrades the Git remote helper when needed and reuses it across jobs.
Buildkite's Git credential integration handles authentication; no Entire login
or token configuration is needed. There are no plugin options.

Requires Buildkite's Entire checkout integration on hosted agents, with Agent
4.3.0 or later.
Automatic installation supports Linux amd64 and arm64, with Bash, curl, Git,
GNU coreutils, sed, and tar.

## License

[MIT](LICENSE)
