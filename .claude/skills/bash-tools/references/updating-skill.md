# Updating This Skill

Guide for extending the bash-tools skill when encountering new issues.

## When to Update

Update this skill when:
- New permission circumvention patterns are discovered
- Tool behavior changes
- New tools are added that affect file operations
- Common mistakes need documentation

## Adding New Circumvention Patterns

When you discover a new Bash pattern that bypasses Write/Edit permissions:

1. **Document in permission-patterns.md:**
   ```markdown
   ### Pattern Name
   ```bash
   # WRONG - bypasses X permissions
   the-command-pattern
   ```
   **Correct:** Use [Tool] tool
   ```

2. **Add to SKILL.md prohibited table** if it's common enough

3. **Test the documentation** - ensure it's clear why the pattern is wrong

## Adding New Tool References

When a new tool affects file operations:

1. Create `references/new-tool.md` with:
   - When to use
   - Parameters
   - Examples
   - Common mistakes
   - Relationship to other tools

2. Add to SKILL.md Tool References section

3. Update decision tree if needed

## Updating Existing References

When tool behavior changes:

1. Read the current reference file
2. Update affected sections
3. Add changelog note at bottom if significant

## Reference File Template

```markdown
# [Tool] Tool Reference

The [Tool] tool [brief description].

## When to Use

- Use case 1
- Use case 2

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|

## Examples

[Concrete examples]

## Common Mistakes

| Mistake | Why | Fix |
|---------|-----|-----|

## Relationship to Other Tools

| Scenario | Tool |
|----------|------|
```

## File Structure

```
bash-tools/
├── SKILL.md                 # Main skill (< 200 lines)
└── references/
    ├── write-tool.md        # Write tool docs
    ├── bash-tool.md         # Bash tool docs
    ├── edit-tool.md         # Edit tool docs
    ├── read-tool.md         # Read tool docs
    ├── permission-patterns.md # Circumvention patterns
    └── updating-skill.md    # This file
```

## Style Guidelines

- Use imperative form ("Use X" not "You should use X")
- Keep SKILL.md under 200 lines
- Keep reference files under 200 lines each
- Use tables for quick reference
- Include concrete examples
- Document the "why" not just the "what"

## Testing Changes

After updating:
1. Review that SKILL.md stays under 200 lines
2. Ensure all referenced files exist
3. Check links work: `[text](references/file.md)`
4. Validate with quick_validate.py if available
