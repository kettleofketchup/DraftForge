# Contributing

## Development Workflow

1. **Fork & Clone**
   ```bash
   git clone https://github.com/YOUR_USERNAME/dota_tournament.git
   ```

2. **Setup Environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   poetry install
   cd frontend && npm install && cd ..
   ```

3. **Create Branch**
   ```bash
   git checkout -b feature/your-feature
   ```

4. **Start Development**
   ```bash
   inv dev.debug
   ```

5. **Run Tests**
   ```bash
   inv test.setup
   inv test.headless
   ```

6. **Commit & Push**
   ```bash
   git add .
   git commit -m "feat: your feature description"
   git push origin feature/your-feature
   ```

7. **Create Pull Request**

## Code Standards

### Python (Backend)

- Follow PEP 8
- Use type hints
- Run with `DISABLE_CACHE=true` for management commands

### TypeScript (Frontend)

- Use Zod for API validation
- Use Shadcn UI components
- Follow hook naming: `<what><action>Hook.tsx`
- Use `getLogger()` for logging

## Commit Messages

Follow conventional commits:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `refactor:` Code refactoring
- `test:` Adding tests
- `chore:` Maintenance

## Pull Request Guidelines

- Include description of changes
- Reference related issues
- Ensure tests pass
- Update documentation if needed
