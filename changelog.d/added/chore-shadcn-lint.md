- Frontend design-system lint with `@shadcn/lint`: new raw Tailwind palette colours
  and classes that generate no CSS now fail a pre-commit hook and a
  `Frontend shadcn lint` CI check. Existing violations are baselined in
  `frontend/shadcn-lint-suppressions.json`, which can only shrink.
