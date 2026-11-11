- The frontend reports to Sentry only when built with `VITE_SENTRY_ENABLED=true`, which the
  production image build sets by default. Dev servers, test stacks and unit tests no longer
  send events to the project's Sentry. `VITE_SENTRY_DSN` optionally overrides the DSN.
