- A captain's connect or disconnect write that waits on the database lock no longer
  freezes WebSocket connects and messages for every other team and hero draft on the
  server. Draft sockets shared one database thread, so a spectator joining an unrelated
  draft waited the full lock wait (about 2.8 seconds behind a 3-second lock in testing);
  it now gets its initial state in under 20 ms. Writes for the same draft still apply in
  the order they were made.
