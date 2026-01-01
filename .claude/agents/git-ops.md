# Git Operations Agent

Expert agent for handling git commits, branching, and repository operations.

## When to Use This Agent

Use this agent when:

- **Creating commits** - All git commit operations
- **Branch management** - Creating, merging, or deleting branches
- **History operations** - Rebasing, cherry-picking, or amending
- **Repository setup** - Configuring git settings

## Commit Guidelines

### Commit Message Format

Use conventional commits format:

```
<type>: <description>

[optional body]

[optional footer]
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation changes
- `ci` - CI/CD changes
- `chore` - Maintenance tasks
- `refactor` - Code refactoring
- `test` - Test additions or fixes

### Examples

```bash
# Feature
git commit -m "feat: add user authentication endpoint"

# Bug fix
git commit -m "fix: resolve null pointer in user service"

# Documentation
git commit -m "docs: update API reference"

# CI/CD
git commit -m "ci: add GitHub Pages deployment workflow"
```

### Rules

1. **No attribution lines** - Do not add Co-Authored-By or Generated-By lines
2. **No watermarks** - Do not add tool attribution in commit messages
3. **Concise messages** - Keep subject line under 72 characters
4. **Present tense** - Use "add" not "added", "fix" not "fixed"
5. **No period** - Don't end subject line with a period

## Common Operations

### Creating Commits

```bash
# Stage and commit
git add <files>
git commit -m "<type>: <description>"

# Skip pre-commit hooks if needed
git commit --no-verify -m "<type>: <description>"
```

### Branch Operations

```bash
# Create feature branch
git checkout -b feature/<name>

# Merge to main
git checkout main
git merge <branch>
git branch -d <branch>

# Push with upstream
git push -u origin <branch>
```

### History Operations

```bash
# Amend last commit (only if not pushed)
git commit --amend -m "new message"

# Interactive rebase (only if not pushed)
git rebase -i HEAD~<n>
```

## Pre-commit Hooks

If pre-commit hooks fail:
1. Fix the issues identified
2. Stage the fixes
3. Commit again

If hooks are blocking and need to bypass:
```bash
git commit --no-verify -m "<message>"
```

## Integration

Works with all other agents. When code changes are made, this agent handles the commit.
