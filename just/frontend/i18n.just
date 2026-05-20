# i18n key extraction and validation

frontend := source_directory() / ".." / ".." / "frontend"

# Extract t() calls and update locale JSONs (writes files)
[group('i18n')]
extract:
    cd "{{frontend}}" && npm run i18n:extract

# Verify locale JSONs match t() calls (CI: fail on diff)
[group('i18n')]
check:
    cd "{{frontend}}" && npm run i18n:check

# Grep guard for untranslated visible prop strings in navbar/
[group('i18n')]
guard:
    cd "{{frontend}}" && npm run i18n:guard
