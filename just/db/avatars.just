# Committed Discord avatars for the real test users (tests/data/discord_avatars.py)

set shell := ["bash", "-euo", "pipefail", "-c"]

root := clean(source_directory() / "../..")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")

# Refetch avatar hashes with DISCORD_BOT_TOKEN from backend/.env and rewrite the data file
[group('db::avatars')]
refresh:
    {{just}} db::manage test refresh_test_avatars
