- CI skips Playwright when a change touches only docs, changelog fragments, root markdown,
  the Helm chart or unrelated workflows; shellcheck runs only when recipes change; the docs
  site redeploys only when docs or their toolchain change.
