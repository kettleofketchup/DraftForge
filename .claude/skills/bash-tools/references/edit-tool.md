# Edit Tool Reference

The Edit tool performs exact string replacements in files.

## When to Use

- Modifying specific parts of existing files
- Updating function implementations
- Changing configuration values
- Adding/removing code blocks

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `file_path` | Yes | - | Absolute path to file |
| `old_string` | Yes | - | Exact text to replace |
| `new_string` | Yes | - | Replacement text |
| `replace_all` | No | false | Replace all occurrences |

## Requirements

1. **Read first**: Must read file before editing
2. **Exact match**: `old_string` must match file exactly
3. **Unique match**: `old_string` must be unique unless `replace_all: true`
4. **Preserve indentation**: Match exact whitespace from file

## Common Failures

| Error | Cause | Fix |
|-------|-------|-----|
| "old_string not found" | Text doesn't exist | Re-read file, copy exact text |
| "old_string not unique" | Multiple matches | Add more context or use `replace_all` |
| "Must read file first" | Skipped Read step | Read the file first |

## Indentation Handling

When reading a file, line numbers appear as prefix. Everything AFTER the tab is actual content:

```
   42→    def example():
```

The `    def example():` (with 4 spaces) is the actual file content. Match this exactly in `old_string`.

## Examples

**Add import:**
```
old_string: |
  import os
  import sys
new_string: |
  import os
  import sys
  import json
```

**Update function:**
```
old_string: |
  def get_name():
      return "old"
new_string: |
  def get_name():
      return "new"
```

**Rename variable (all occurrences):**
```
old_string: oldVarName
new_string: newVarName
replace_all: true
```

## When to Use Write Instead

| Scenario | Tool |
|----------|------|
| Change < 50% of file | Edit |
| Change > 50% of file | Write |
| Complete rewrite | Write |
| New file | Write |
