# Discord bot commands

root := source_directory() / ".."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('discord')]
ngrok port="443":
    {{inv}} discord.ngrok --port {{port}}

[group('discord')]
logs stack="dev":
    {{inv}} discord.logs --stack {{stack}}
