# Maintenance

- Run `shellcheck hooks/*` and `python3 -B -m unittest discover -s tests -v`.
  Tests download pinned Entire and Agent binaries and use OpenSSL for a local
  TLS fixture; no live credentials are used.
- Only `BUILDKITE_COMPUTE_TYPE=hosted` acquires the selected-repository token,
  once, and exports it as `ENTIRE_TOKEN`. Do not configure Git credentials or
  change operator authentication on other compute types. Never log or write the
  fetched token to a file, or export it through another variable. Disable shell
  tracing around acquisition/export and suppress untrusted agent diagnostics.
- The pinned [upstream commit](https://github.com/entireio/cli/commit/a564a68c802d50a0f4cff333da6ee13d59be027d)
  is validated against the environment-token flow. Update both architecture
  checksums and the version tests together; unknown development versions are
  replaced because commit hashes cannot establish version order.
- `ENTIRE_TOKEN` selects a fixed bearer with no login fallback or token refresh.
  Entire's server enforces repository scope; the plugin does not filter later
  requests. Tests use an Entire fixture, not live Entire, and cannot prove live
  token scope enforcement. Keep those limits explicit when reporting compatibility.
