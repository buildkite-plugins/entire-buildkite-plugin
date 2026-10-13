# Entire Buildkite Plugin

Check out [Entire](https://entire.io) repositories with Buildkite.

```yaml
steps:
  - command: ./test.sh
    plugins:
      - entire#v1.0.0: ~
```

Installs or upgrades the Git remote helper when needed and reuses it across jobs.
Buildkite's Git credential integration handles authentication; no Entire login
or token configuration is needed. There are no plugin options.

Requires an agent with native Entire checkout support. Automatic installation
supports Linux amd64 and arm64, with Bash, curl, Git, GNU coreutils, and tar.

**Not released yet.** The example shows the planned first-party release.

## License

[MIT](LICENSE)
