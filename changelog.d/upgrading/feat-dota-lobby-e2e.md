Test stacks now run with dota_lobby lobbies on (`docker/.env.test`): `DOTA_LOBBY_URL`
points at the stack's simulated `dota-lobby` service, and `DOTA_LOBBY_API_KEY`,
`DOTA_LOBBY_WEBHOOK_SECRET` and `INTERNAL_SERVICE_TOKEN` are test-only values that
replace the ones in `backend/.env` for test stacks. Backend unit tests still start with
lobbies off. Repopulate the test database (`just db::populate::fresh`) for the
dota_lobby test data.

The simulator image is `DOTA_LOBBY_IMAGE`, by default
`ghcr.io/kettleofketchup/dota_lobby:${DOTA_LOBBY_IMAGE_TAG}`, whose default tag is a
placeholder until the first dota_lobby release with simulation mode. Until then, build
it in dota_lobby (`just docker::build`) and run
`DOTA_LOBBY_IMAGE=ghcr.io/kettleofketchup/dota_lobby:local just test::dota-lobby up`.
With it running, `just test::pw::dota-lobby` and `cicd-dota-lobby` set
`DOTA_LOBBY_SIMULATOR_REQUIRED=1`: a simulator that never becomes available fails the
run instead of skipping its specs.
