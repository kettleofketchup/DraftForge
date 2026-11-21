- Test stack slots: idle slots are auto-reaped again. Redis logs every periodic save and
  celery runs scheduled tasks, so their log lines made every running stack look active and
  `just test::upd` failed with "no free test slot". Only `backend`, `frontend` and `nginx`
  logs now count as activity; container starts and stops still count for every service.
