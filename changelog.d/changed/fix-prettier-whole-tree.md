- The `Frontend format` CI job now checks the whole frontend with Prettier, on pull
  requests and on pushes to `main`. It used to check only the files a PR changed, so
  unformatted files stayed on `main` and failed later PRs that touched them (#742).
