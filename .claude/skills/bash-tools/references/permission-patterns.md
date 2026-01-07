# Permission Circumvention Patterns

This document catalogs patterns that attempt to bypass file operation permissions.

**All of these are PROHIBITED.** Use proper tools instead.

## File Creation Bypasses

### Echo Redirect
```bash
# WRONG - bypasses Write permissions
echo "def main():" > script.py
echo "    print('hello')" >> script.py
```
**Correct:** Use Write tool

### Heredoc/Here-document
```bash
# WRONG - bypasses Write permissions
cat << 'EOF' > config.yaml
database:
  host: localhost
  port: 5432
EOF
```
**Correct:** Use Write tool

### Printf Redirect
```bash
# WRONG - bypasses Write permissions
printf '%s\n' "line1" "line2" > file.txt
```
**Correct:** Use Write tool

### Tee Command
```bash
# WRONG - bypasses Write permissions
echo "content" | tee newfile.txt
tee newfile.txt <<< "content"
```
**Correct:** Use Write tool

### Cat Concatenation
```bash
# WRONG - bypasses Write permissions
cat file1.txt file2.txt > combined.txt
```
**Correct:** Read both files, use Write tool for combined

## File Modification Bypasses

### Sed In-place
```bash
# WRONG - bypasses Edit permissions
sed -i 's/old/new/g' file.txt
sed -i '1iNew first line' file.txt
```
**Correct:** Use Edit tool

### Awk Modification
```bash
# WRONG - bypasses Edit permissions
awk '{gsub(/old/,"new")}1' file.txt > temp && mv temp file.txt
```
**Correct:** Use Edit tool

### Perl One-liner
```bash
# WRONG - bypasses Edit permissions
perl -i -pe 's/old/new/g' file.txt
```
**Correct:** Use Edit tool

### Ed/Ex Commands
```bash
# WRONG - bypasses Edit permissions
ed -s file.txt <<< $'1s/old/new/\nw'
```
**Correct:** Use Edit tool

## File Reading Bypasses

These are less critical but still wrong:

```bash
# Use Read tool instead of:
cat file.txt
head -n 100 file.txt
tail -n 50 file.txt
less file.txt
more file.txt
```

## Search Bypasses

```bash
# Use Grep tool instead of:
grep "pattern" file.txt
rg "pattern" .
ack "pattern"
```

```bash
# Use Glob tool instead of:
find . -name "*.py"
ls **/*.js
```

## Why This Matters

1. **User control**: Permissions let users control what changes
2. **Auditability**: Tool usage is tracked and reviewable
3. **Safety**: Prevents accidental file modifications
4. **Transparency**: User sees what's being changed

When permissions block an operation:
1. Accept the block
2. Ask user if they want to allow it
3. Never work around it with Bash

## Adding New Patterns

When you encounter a new circumvention pattern:
1. Document it in this file
2. Add the command pattern
3. Note what proper tool to use instead
4. See [updating-skill.md](updating-skill.md) for process
