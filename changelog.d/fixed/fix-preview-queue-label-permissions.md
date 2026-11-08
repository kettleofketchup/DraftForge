- Closing or merging a pull request that holds a preview slot no longer fails the
  `preview-queue` workflow with HTTP 403: its jobs can now remove the `preview-env` label
  from pull requests, so the slot is released.
