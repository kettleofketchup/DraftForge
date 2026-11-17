- The daily batched avatar refresh works again: Celery workers now receive the Discord
  API settings they need.
- Refresh members now refetches the member list from Discord instead of reusing the
  cached copy, and applies the names it gets.
- Captain name search in match suggestions and user search in the OrgUser and
  LeagueUser admin no longer error.
