- **Helm chart and per-PR previews.** A `draftforge` Helm chart (`helm/`) and the CI
  that builds preview images and queues PRs for a preview environment
  (`draftforge-pr-<n>`). In preview mode the chart requires the deploying cluster to
  set every resource quota, LimitRange and rate limit. See `helm/README.md`.
