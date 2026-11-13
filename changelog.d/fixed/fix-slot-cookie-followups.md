- The frontend now learns the CSRF cookie name from the backend's `X-CSRF-Cookie-Name`
  response header, so a frontend built or started with a different name no longer
  fails every write with a 403 on a test stack slot.
- Browser cookie reads share one exact-match reader that URL-decodes values.
