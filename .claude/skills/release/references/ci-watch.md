# Watching the release CI

The version tag triggers `release-docker-images.yml`. Watch it with `gh`.

## Find the run

```bash
# the run kicked off by the tag push (most recent)
gh run list --workflow=release-docker-images.yml --limit 3
```
Columns: status, name, branch/event, ID. The tag push shows event `push` with the
tag as the ref. Grab the run ID.

## Watch to completion

```bash
gh run watch <run-id> --exit-status   # blocks, non-zero exit if the run fails
```
`--exit-status` makes the command fail when the run fails, so it's safe to branch on.

If not blocking, just report the URL:
```bash
gh run view <run-id> --json url,status,conclusion -q '.url'
```

## On failure

```bash
gh run view <run-id> --log-failed    # only the failed steps' logs
```
Common failures: GHCR auth/permissions, a Dockerfile build error, or the
"Validate version tag" step rejecting a malformed tag. Report the failing job +
step and the relevant log lines; don't retry blindly.

## Confirm images landed

The workflow pushes to `ghcr.io/kettleofketchup/draftforge/{backend,frontend,nginx}`
tagged with the version. Verify via the run's push step output, or:
```bash
gh api "/orgs/kettleofketchup/packages/container/draftforge%2Fbackend/versions" \
  --jq '.[0].metadata.container.tags'   # newest tags first
```
(Adjust owner/package; org vs user endpoint differs — fall back to reading the run's
push log if the API path 404s.)
