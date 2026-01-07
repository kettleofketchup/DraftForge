# Write Tool Reference

The Write tool creates or overwrites files with specified content.

## When to Use

- Creating new files from scratch
- Completely replacing file contents
- Writing generated code, configs, or data files

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `file_path` | Yes | Absolute path to file (not relative) |
| `content` | Yes | Full content to write |

## Requirements

1. **Read before write**: Must read existing files before overwriting
2. **Absolute paths only**: Relative paths not accepted
3. **No unnecessary files**: Prefer editing existing files

## Example Usage

```
Write tool:
- file_path: /home/user/project/config.py
- content: |
    # Configuration file
    DEBUG = True
    PORT = 8080
```

## Common Mistakes

| Mistake | Why | Fix |
|---------|-----|-----|
| Using relative path | Tool requires absolute | Use full path from root |
| Not reading first | Overwrites need read first | Read file before Write |
| Creating when editing works | Unnecessary file creation | Use Edit instead |

## Permission Blocked?

If Write is blocked for a path:

1. **Do not use Bash alternatives** (`echo`, `cat`, heredoc)
2. Ask user if operation should be allowed
3. Check if Edit tool would work instead

The permission system is intentional. Never circumvent it.

## Relationship to Other Tools

| Scenario | Tool |
|----------|------|
| New file / full replace | Write |
| Partial modification | Edit |
| Append to file | Edit (match last line, add content) |
| Read content | Read |
