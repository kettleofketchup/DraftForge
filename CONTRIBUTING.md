# Contributing to DTX Website

## Getting Started

1. Fork the repository
2. Clone your fork
3. Set up the development environment:
   ```bash
   source .venv/bin/activate
   inv dev.debug
   ```

## Development Workflow

1. Create a feature branch from `main`
2. Make your changes
3. Run tests: `inv dev.test`
4. Commit with conventional commit messages
5. Push and create a pull request

## Commit Message Format

Use conventional commits:

```
<type>: <description>

[optional body]
```

Types: `feat`, `fix`, `docs`, `ci`, `chore`, `refactor`, `test`

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
