# Maintenance

- README.md is end-user documentation: keep purpose, usage, requirements, and
  actionable limitations concise. Requirements there are runtime dependencies
  only. Do not add contributor workflows, lint-only examples, or unreleased/
  development framing to satisfy CI. Do not add review history or speculative support.
- Put development requirements, check commands, and linter examples in
  CONTRIBUTING.md; keep implementation invariants in AGENTS.md. Run all checks
  documented in CONTRIBUTING.md before completing changes.
- Use `--id entire --readme CONTRIBUTING.md` in both CI and the documented
  plugin-linter command. Keep the README's unversioned end-user example; fix
  linter configuration rather than changing user guidance to satisfy discovery.
  Fetch tags for version checks and follow CONTRIBUTING.md when updating refs.
  Never use skip flags to bypass example or version validation.
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
- v0.11.5 removed Git credential lookup and `ENTIRE_GIT_NO_LOGIN_FALLBACK`.
  When `ENTIRE_TOKEN` is unset, the hook must fail closed for an explicit login
  opt-out or invalid boolean, matching the old helper's `strconv.ParseBool`
  semantics. An absent opt-out allows saved login. A present token takes
  precedence; the helper rejects an empty token without using saved login.
- The pinned [v0.11.5 commit](https://github.com/entireio/cli/commit/4b8cdfaf0d15e236835c3b7c85d8803b112574bc)
  is validated against the environment-token flow and `GIT_HTTP_USER_AGENT`.
  Commit artifacts report `0.0.0+<commit>`, not the release version. Update both
  architecture checksums and the version tests together; unknown development
  versions are replaced because commit hashes cannot establish version order.
- The pinned helper [consumes `ENTIRE_TOKEN` as a fixed JWT bearer](https://github.com/entireio/cli/blob/4b8cdfaf0d15e236835c3b7c85d8803b112574bc/cmd/git-remote-entire/main.go#L364-L386),
  bypassing Git credentials and saved login, with no token refresh. The bearer
  can be sent to other repositories in a trusted cluster. Entire's server must
  enforce repository scope; the plugin does not filter later requests.
  Tests use an Entire fixture, not live Entire, and cannot prove live
  token scope enforcement. Keep those limits explicit when reporting compatibility.
