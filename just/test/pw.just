# Playwright test commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('test::pw')]
headless *args:
    {{inv}} test.playwright.headless {{ if args != "" { "--args='" + args + "'" } else { "" } }}

[group('test::pw')]
headed *args:
    {{inv}} test.playwright.headed {{ if args != "" { "--args='" + args + "'" } else { "" } }}

[group('test::pw')]
ui:
    {{inv}} test.playwright.ui

[group('test::pw')]
debug:
    {{inv}} test.playwright.debug

[group('test::pw')]
spec pattern:
    {{inv}} test.playwright.spec --spec '{{pattern}}'

[group('test::pw')]
file path:
    {{inv}} test.playwright.spec --file '{{path}}'

[group('test::pw')]
install:
    {{inv}} test.playwright.install

[group('test::pw')]
report:
    {{inv}} test.playwright.report

[group('test::pw')]
navigation *args:
    {{inv}} test.playwright.navigation {{ if args != "" { "--args='" + args + "'" } else { "" } }}

[group('test::pw')]
tournament *args:
    {{inv}} test.playwright.tournament {{ if args != "" { "--args='" + args + "'" } else { "" } }}

[group('test::pw')]
draft *args:
    {{inv}} test.playwright.draft {{ if args != "" { "--args='" + args + "'" } else { "" } }}

[group('test::pw')]
bracket *args:
    {{inv}} test.playwright.bracket {{ if args != "" { "--args='" + args + "'" } else { "" } }}

[group('test::pw')]
league *args:
    {{inv}} test.playwright.league {{ if args != "" { "--args='" + args + "'" } else { "" } }}

[group('test::pw')]
herodraft *args:
    {{inv}} test.playwright.herodraft {{ if args != "" { "--args='" + args + "'" } else { "" } }}

[group('test::pw')]
herodraft-headed:
    {{inv}} test.playwright.herodraft-headed

[group('test::pw')]
all *args:
    {{inv}} test.playwright.all {{ if args != "" { "--args='" + args + "'" } else { "" } }}

# Run only @cicd tagged tests (fast smoke tests for CI/CD)
[group('test::pw')]
cicd *args:
    {{inv}} test.playwright.cicd {{ if args != "" { "--args='" + args + "'" } else { "" } }}
