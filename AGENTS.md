# Maintenance

- Run `shellcheck hooks/*` and `python3 -B -m unittest discover -s tests -v`.
  Tests download pinned Entire and Agent binaries; no live credentials are used.
- Git and the agent own authentication. The job-local adapter changes only the
  credential protocol to HTTPS for older agents; never export or persist tokens.
- The pinned [upstream commit](https://github.com/entireio/cli/commit/a564a68c802d50a0f4cff333da6ee13d59be027d)
  is the first native credential-helper build. Stable 0.11.4 is too old. Update
  both architecture checksums and the version tests together; unknown development
  versions are replaced because commit hashes cannot establish version order.
- Before the first `buildkite-plugins` release, verify combined agent/Rails checkout,
  squash the development history, and remove the README's unreleased notice.
  Do not rewrite published history or promote the repository without approval.
