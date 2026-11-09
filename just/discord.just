# Discord bot commands

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
slots := quote(python) + " -m scripts.slots --root " + quote(root)

# Tunnel a local port (default 443, nginx) with ngrok for Discord interactions
[group('discord')]
ngrok port="443":
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Starting ngrok tunnel for Discord interactions..."
    echo
    echo "After ngrok starts:"
    echo "1. Copy the HTTPS 'Forwarding' URL (e.g., https://abc123.ngrok.io)"
    echo "2. Go to Discord Developer Portal > Your App > General Information"
    echo "3. Set 'Interactions Endpoint URL' to: <ngrok-url>/discord/interactions/"
    echo "4. Discord will send a PING to verify - check backend logs for confirmation"
    echo
    # --host-header keeps the Host nginx expects for the self-signed cert.
    exec ngrok http "https://localhost:$1" --host-header=localhost

# Follow the Discord bot's logs (stack: dev, the one ngrok serves, or test)
[group('discord')]
logs stack="dev":
    cd {{quote(root)}} && {{slots}} compose --stack "$1" logs -f --tail=100 discord-bot
