- nginx now keeps connections to the frontend open and reuses them. Before, it opened a
  new connection for every proxied request. Under the Vite dev server (hundreds of
  module requests per page) these piled up in `TIME_WAIT` and used up nginx's ephemeral
  ports. nginx then returned 502 for documents, `__manifest` and module chunks. Pages
  stayed on their server-rendered loading state (e.g. "Loading organization...") and
  `17-auth` role-matrix specs timed out on first attempt.
