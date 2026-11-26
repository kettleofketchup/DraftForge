- `just test::affected` runs only the backend tests and Vitest files a branch's
  changes can reach, widening to whole apps or the full suite where imports can't
  tell; `--plan` prints the selection and why. The full suites and CI remain the gate.
