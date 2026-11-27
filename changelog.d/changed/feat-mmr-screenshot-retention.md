- MMR request screenshots are deleted 7 days after the request is approved, rejected
  or superseded; the request row stays as the audit record. A nightly task does the
  purge, and the staff card says "Screenshot removed after N days" instead of showing
  a broken image. Set `MMR_SCREENSHOT_RETENTION_DAYS` to change the window.
