- The `PositionsModel` and `ProfileClaimRequest` models moved from `app` into
  the `user` Django app (`user.models`). The migrations are state-only: the
  `app_positionsmodel` and `app_profileclaimrequest` tables, their index and
  constraint names and the `user_dotauserprofile.positions_id` foreign key are
  unchanged, and no schema changes on deploy.
- The two ContentType rows are relabelled from `app` to `user` with their ids
  kept, so the model labels `app.positionsmodel` and `app.profileclaimrequest`
  are now `user.positionsmodel` and `user.profileclaimrequest`, and permission
  codenames such as `app.add_positionsmodel` and
  `app.change_profileclaimrequest` are now `user.add_positionsmodel` and
  `user.change_profileclaimrequest`. Existing user and group grants carry over.
- Neither model has an admin or a cacheops profile, so no admin URLs or cache
  keys change. HTTP and WebSocket paths, payloads and table names are
  unchanged.
