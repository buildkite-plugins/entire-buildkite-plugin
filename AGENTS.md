# Maintenance

- Run `shellcheck hooks/*` and `python3 -B -m unittest discover -s tests -v`.
  Tests download pinned Entire and Agent binaries; no live credentials are used.
- Only `BUILDKITE_COMPUTE_TYPE=hosted` installs the repository-bound adapter for
  the known agent helper and disables saved-login fallback. Other compute types
  retain their credential configuration and fallback policy. Never capture or
  replay operator helpers, or export or persist tokens.
- The pinned [upstream commit](https://github.com/entireio/cli/commit/a564a68c802d50a0f4cff333da6ee13d59be027d)
  is the first native credential-helper build. Stable 0.11.4 is too old. Update
  both architecture checksums and the version tests together; unknown development
  versions are replaced because commit hashes cannot establish version order.
- Combined agent/server checkout has been tested against an Entire fixture, not
  live Entire. Keep that distinction when reporting compatibility.
