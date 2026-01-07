# Bash Tool Reference

The Bash tool executes shell commands in a persistent session.

## When to Use

- Git operations: `git add`, `git commit`, `git push`
- Package managers: `npm`, `yarn`, `pip`, `poetry`
- Build tools: `make`, `docker`, `cargo`
- Running tests and scripts
- System commands that don't modify file contents

## When NOT to Use

| Task | Wrong | Correct |
|------|-------|---------|
| Create file | `echo "x" > file` | Write tool |
| Edit file | `sed -i 's/x/y/' file` | Edit tool |
| Read file | `cat file` | Read tool |
| Search content | `grep pattern` | Grep tool |
| Find files | `find . -name` | Glob tool |

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `command` | Yes | - | Shell command to execute |
| `description` | No | - | 5-10 word description |
| `timeout` | No | 120000 | Max time in ms (max 600000) |
| `run_in_background` | No | false | Run without blocking |

## Prohibited Patterns

**Never use Bash to write file contents:**

```bash
# ALL OF THESE ARE WRONG - Use Write tool instead
echo "content" > file.py
cat << 'EOF' > file.py
content
EOF
printf '%s' "$content" > file.py
tee file.py <<< "content"
```

See [permission-patterns.md](permission-patterns.md) for complete list.

## Proper Usage Examples

```bash
# Git operations - OK
git status
git add .
git commit -m "message"

# Package management - OK
npm install
pip install -r requirements.txt

# Running commands - OK
make build
docker compose up -d
pytest tests/

# Directory operations - OK
mkdir -p src/components
```

## Chaining Commands

```bash
# Independent commands - run in parallel (separate tool calls)
# Dependent commands - chain with &&
git add . && git commit -m "msg" && git push
```

## Background Execution

For long-running commands:
```
Bash tool:
- command: npm run dev
- run_in_background: true
```

Use TaskOutput to check results later.
