- End-to-end tests of the dota_lobby integration against the real dota_lobby service in
  simulation mode: the test stack's `dota-lobby` service (`just test::dota-lobby up`,
  compose profile `dota-lobby`) and the `18-dota-lobby` Playwright specs (lobby
  passwords, who sees them, the lobby lifecycle and the match dialog's fit on small
  screens), with their own test data and `/api/tests/dota-lobby*` endpoints.
