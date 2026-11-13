- The `df-locale` language cookie is now written as the plain locale (`es`) by both the
  server and the browser. Before, the server wrote base64 JSON (`ImVzIg==`) and the
  browser wrote the plain value, so a language chosen on one side could be ignored by
  the other. Cookies already saved in the old format are still honoured and are
  rewritten in the plain format on the next visit.
