# Read Tool Reference

The Read tool reads file contents from the filesystem.

## When to Use

- Viewing file contents before editing
- Understanding code structure
- Checking configuration values
- Reading images, PDFs, notebooks (multimodal)

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `file_path` | Yes | - | Absolute path to file |
| `offset` | No | 0 | Starting line number |
| `limit` | No | 2000 | Max lines to read |

## Output Format

Lines displayed with `cat -n` style numbering:
```
     1→first line
     2→second line
```

The arrow (→) separates line number from content. Content after → is the actual file text.

## Supported File Types

| Type | Behavior |
|------|----------|
| Text files | Returns content with line numbers |
| Images (.png, .jpg) | Visual display (multimodal) |
| PDFs (.pdf) | Page-by-page text + visual |
| Notebooks (.ipynb) | All cells with outputs |
| Directories | Error - use `ls` via Bash |

## Large Files

For files > 2000 lines, use `offset` and `limit`:

```
Read tool:
- file_path: /path/to/large.py
- offset: 100
- limit: 50
```

Reads lines 100-149.

## Why Not cat/head/tail?

| Bash Command | Problem |
|--------------|---------|
| `cat file` | No permission tracking |
| `head -n 50 file` | Misses Edit requirements |
| `tail -f file` | Use for logs only |

The Read tool tracks what you've read, enabling Edit operations.

## Before Editing

**Always Read before Edit or Write:**

```
1. Read tool: /path/to/file.py
2. Edit tool: (modify the content)
```

Skipping Read causes "File has not been read yet" error.

## Parallel Reads

Multiple independent reads can run in parallel:
```
Read: /path/file1.py
Read: /path/file2.py
Read: /path/file3.py
```

Send all in one message for efficiency.
