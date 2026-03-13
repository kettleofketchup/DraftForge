# Cloudflare R2 asset storage commands

root := source_directory() / ".."
assets := root / "docs/assets"
bucket := "dfdemos"
prefix := "draftforge"
remote := "draftforge:" + bucket + "/" + prefix

[private]
_r2-auth:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v rclone &>/dev/null; then
        echo "Error: rclone is not installed."
        echo "Install: https://rclone.org/install/"
        exit 1
    fi
    if ! rclone listremotes 2>/dev/null | grep -q '^draftforge:$'; then
        echo "Error: rclone remote 'draftforge:' not configured."
        echo ""
        echo "Run: rclone config"
        echo "  Type: s3"
        echo "  Provider: Cloudflare"
        echo "  Endpoint: https://<account-id>.r2.cloudflarestorage.com"
        exit 1
    fi

# Upload all assets (videos, gifs, snapshots) to R2
[group('r2')]
upload: _r2-auth
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Uploading videos..."
    rclone sync "{{assets}}/videos/" "{{remote}}/videos/" --exclude ".gitkeep" --exclude "*.Identifier" --progress
    echo ""
    echo "Uploading gifs..."
    rclone sync "{{assets}}/gifs/" "{{remote}}/gifs/" --exclude ".gitkeep" --progress
    echo ""
    echo "Uploading snapshots..."
    rclone sync "{{assets}}/site_snapshots/" "{{remote}}/site_snapshots/" --exclude ".gitkeep" --progress
    echo ""
    echo "All assets uploaded to https://assets.kettle.sh/{{prefix}}/"

# Upload only videos
[group('r2')]
upload-videos: _r2-auth
    rclone sync "{{assets}}/videos/" "{{remote}}/videos/" --exclude ".gitkeep" --exclude "*.Identifier" --progress

# Upload only gifs
[group('r2')]
upload-gifs: _r2-auth
    rclone sync "{{assets}}/gifs/" "{{remote}}/gifs/" --exclude ".gitkeep" --progress

# Upload only snapshots
[group('r2')]
upload-snapshots: _r2-auth
    rclone sync "{{assets}}/site_snapshots/" "{{remote}}/site_snapshots/" --exclude ".gitkeep" --progress

# List all uploaded assets
[group('r2')]
ls *args: _r2-auth
    rclone ls "{{remote}}/" {{args}}
