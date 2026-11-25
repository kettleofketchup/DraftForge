- The feature pipeline runs affected tests while iterating instead of whole apps,
  reviewers stop repeating the implementer's suites unless something changed, tasks
  that only touch docs, the changelog or copy skip per-task review, and the Verify
  phase runs backend/E2E and frontend/docs checks in parallel. Spec and plan review
  can repeat with `specCycles`/`planCycles`.
