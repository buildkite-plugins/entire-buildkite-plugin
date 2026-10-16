# Contributing

## Development requirements

Use Linux amd64 or arm64 with the [runtime dependencies](README.md#runtime-requirements),
Python 3, OpenSSL, ShellCheck, and Docker. Tests download pinned Entire and
Buildkite Agent binaries and use a local TLS fixture; no live credentials are needed.

## Checks

Run from the repository root:

```sh
git fetch --tags origin
shellcheck -x hooks/* bin/* lib/*
python3 -B -m unittest discover -s tests -v
docker run --rm -v "$PWD:/plugin:ro" buildkite/plugin-linter --id entire --readme CONTRIBUTING.md
```

## Linter example

The linter validates this example instead of the end-user README. Its example
discovery requires an explicit ref; `main` is a development branch, not a release.

```yaml
plugins:
  - entire#main: {}
```

The linter compares refs with local release tags. At the first release, replace
`main` above with the actual tag; update it on later releases. Do not bypass
example or version validation with skip flags.
