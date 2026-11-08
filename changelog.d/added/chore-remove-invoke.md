- **Shellcheck gate.** `just ci::shellcheck` renders every just recipe with `--dry-run`
  and runs ShellCheck 0.11.0 on it under the shell it runs with; the `shellcheck`
  workflow runs it on every pull request.
