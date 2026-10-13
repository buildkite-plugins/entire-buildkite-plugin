# Maintenance

- README.md is end-user documentation: keep purpose, usage, requirements, and
  actionable limitations concise. Put implementation and testing details in
  AGENTS.md, not the README. Do not add review history or speculative support.
- Run `shellcheck hooks/*` and `python3 -B -m unittest discover -s tests -v`.
  Tests download pinned Entire and Agent binaries and use OpenSSL for a local
  TLS fixture; no live credentials are used.
- Only `BUILDKITE_COMPUTE_TYPE=hosted` acquires the selected-repository token,
  once, and exports it as `ENTIRE_TOKEN`. Do not configure Git credentials or
  change operator authentication on other compute types. Never log or write the
  fetched token to a file, or export it through another variable. Disable shell
  tracing around acquisition/export and suppress untrusted agent diagnostics.
- Acquisition calls Agent 4.3.0's internal `git-credentials-helper get` directly
  with the selected repository's exact HTTPS alias, which the issuer authorizes.
  It is not installed as a Git credential helper. Empty/error credentials fail
  the hook with generic diagnostics. Missing/unknown compute types, like
  self-hosted agents, retain operator authentication and fallback policy.
- The pinned [upstream commit](https://github.com/entireio/cli/commit/a564a68c802d50a0f4cff333da6ee13d59be027d)
  is validated against the environment-token flow. Update both architecture
  checksums and the version tests together; unknown development versions are
  replaced because commit hashes cannot establish version order.
- The pinned helper [consumes `ENTIRE_TOKEN` as a fixed JWT bearer](https://github.com/entireio/cli/blob/a564a68c802d50a0f4cff333da6ee13d59be027d/cmd/git-remote-entire/main.go#L368-L392),
  bypassing Git credentials and saved login, with no token refresh. The bearer
  can be sent to other repositories in a trusted cluster. Entire's server must
  enforce repository scope; the plugin does not filter later requests.
  Tests use an Entire fixture, not live Entire, and cannot prove live
  token scope enforcement. Keep those limits explicit when reporting compatibility.
