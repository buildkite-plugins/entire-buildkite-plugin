# Maintenance

- Run `shellcheck hooks/*` and `python3 -B -m unittest discover -s tests -v`.
  Tests download pinned Entire and Agent binaries; no live credentials are used.
- Git owns helper selection and ordering. The job-local filter retains native
  requests for operator helpers and translates only detected agent helpers to
  HTTPS; never export or persist retrieved tokens.
- The pinned [upstream commit](https://github.com/entireio/cli/commit/a564a68c802d50a0f4cff333da6ee13d59be027d)
  is the first native credential-helper build. Stable 0.11.4 is too old. Update
  both architecture checksums and the version tests together; unknown development
  versions are replaced because commit hashes cannot establish version order.
- Combined agent/server checkout has been tested against an Entire fixture, not
  live Entire. Keep that distinction when reporting compatibility.
