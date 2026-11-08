# Contributing to DTX Website

## Getting Started

1. Fork the repository
2. Clone your fork
3. Set up the development environment:
   ```bash
   ./dev   # installs just, creates the venv, starts the dev stack
   ```

## Development Workflow

1. Create a feature branch from `main`
2. Make your changes
3. Run tests: `just test::setup`, then `just test::pw::headless`
4. Add a changelog fragment if users or operators would notice the change (see below)
5. Commit with conventional commit messages
6. Push and create a pull request

## Commit Message Format

Use conventional commits:

```
<type>: <description>

[optional body]
```

Types: `feat`, `fix`, `docs`, `ci`, `chore`, `refactor`, `test`

## Changelog

Do not edit `CHANGELOG.md` in a PR; add a fragment under `changelog.d/` instead and
check it with `python3 scripts/changelog.py check`. The rules are in
[docs/development/changelog.md](docs/development/changelog.md).

## AI Use

This project uses AI-assisted development tools. Guidelines for AI use:

### Commit Attribution

- **All commits are attributed to the human developer** who reviews and approves the changes
- Do not add AI tool attribution (e.g., "Generated with...", "Co-Authored-By: AI...")
- The developer takes responsibility for all committed code

### AI Tool Usage

- AI tools may be used for code generation, documentation, and automation
- All AI-generated code must be reviewed before committing
- The developer is responsible for understanding and maintaining AI-generated code

### Quality Standards

AI-assisted code must meet the same standards as manually written code:
- Passes all tests
- Follows project conventions
- Is properly documented
- Has been reviewed for security issues

## Code Style

- **Python**: Follow PEP 8, use type hints
- **TypeScript**: Follow ESLint configuration
- **Commits**: Use conventional commits format

## Questions?

Open an issue for questions or discussions.
