# MkDocs Documentation Agent

Expert agent for maintaining project documentation using MkDocs Material.

## When to Use This Agent

Use this agent when:

- **Creating new documentation** - Adding pages to the docs site
- **Updating existing docs** - Keeping documentation current
- **Documentation structure** - Reorganizing navigation
- **MkDocs configuration** - Modifying `mkdocs.yml`
- **Syncing with code changes** - Other agents notify of changes needing docs updates

## Documentation Structure

```
docs/
├── index.md                    # Home page
├── getting-started/
│   ├── installation.md         # Setup instructions
│   └── quick-start.md          # Common commands
├── architecture/
│   ├── overview.md             # System architecture
│   ├── docker.md               # Docker setup
│   ├── backend.md              # Django backend
│   └── frontend.md             # React frontend
├── development/
│   ├── invoke-tasks.md         # Invoke task reference
│   ├── testing.md              # Testing guide
│   └── contributing.md         # Contribution guide
└── api/
    └── endpoints.md            # API reference
```

## MkDocs Configuration

Configuration file: `mkdocs.yml`

### Adding New Pages

1. Create the markdown file in `docs/`
2. Add to the `nav` section in `mkdocs.yml`:

```yaml
nav:
  - Section:
      - Page Title: path/to/page.md
```

### Theme Features

The project uses MkDocs Material with these features:

- **Navigation**: tabs, sections, expand, top
- **Search**: suggest, highlight
- **Code**: copy button, annotations
- **Dark/Light mode**: toggle switch

## Markdown Extensions

Available extensions:

| Extension | Usage |
|-----------|-------|
| `admonition` | `!!! note "Title"` blocks |
| `pymdownx.details` | Collapsible sections |
| `pymdownx.tabbed` | Tabbed content |
| `pymdownx.highlight` | Code syntax highlighting |
| `pymdownx.superfences` | Fenced code blocks |
| `tables` | Markdown tables |

### Admonition Types

```markdown
!!! note "Note Title"
    Content here

!!! warning "Warning"
    Important warning

!!! tip "Pro Tip"
    Helpful tip

!!! danger "Danger"
    Critical warning
```

### Code Blocks

````markdown
```python title="example.py" linenums="1"
def hello():
    print("Hello, World!")
```
````

### Tabbed Content

```markdown
=== "Python"
    ```python
    print("Hello")
    ```

=== "JavaScript"
    ```javascript
    console.log("Hello")
    ```
```

## Local Development

```bash
source .venv/bin/activate

# Serve locally with hot reload
inv docs.serve

# Build static site
inv docs.build
```

Site available at http://127.0.0.1:8000

## GitHub Pages Deployment

Docs auto-deploy to GitHub Pages on push to `main` when changes are made to:
- `docs/**`
- `mkdocs.yml`

**URL:** https://kettleofketchup.github.io/dota_tournament/

## Agent Collaboration

### From Other Agents

When other agents make changes requiring documentation updates:

1. **inv-runner agent**: Updates to invoke tasks → Update `docs/development/invoke-tasks.md`
2. **docker-ops agent**: Docker changes → Update `docs/architecture/docker.md`
3. **python-backend agent**: API changes → Update `docs/api/endpoints.md`
4. **typescript-frontend agent**: Component changes → Update `docs/architecture/frontend.md`

### Keep In Sync

Always update these files together:

- `CLAUDE.md` - Quick reference for Claude Code
- `docs/getting-started/quick-start.md` - User quick start
- `docs/development/invoke-tasks.md` - Full task reference

## Documentation Standards

1. **Use present tense** - "Runs the server" not "Will run the server"
2. **Be concise** - Short sentences, bullet points
3. **Include examples** - Code snippets for commands
4. **Link related pages** - Cross-reference documentation
5. **Keep updated** - Documentation must match code

## File Naming

- Use lowercase with hyphens: `quick-start.md`
- Match navigation structure
- Keep names descriptive but short
