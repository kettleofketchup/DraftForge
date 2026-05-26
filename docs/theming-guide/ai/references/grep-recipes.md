# Grep Recipes

Copy-paste `rg` recipes for finding brand violations across the [in-scope](scope.md) tree. Run from the draftforge repo root.

## Define the scope once

```bash
SCOPE=frontend/app
```

Most recipes glob `--glob '!**/components/ui/**'` to skip the bare shadcn primitives (those are out of scope for this skill).

## Buttons

```bash
rg -n '<button[^>]*onClick' "$SCOPE" --glob '!**/components/ui/buttons/**' --glob '!**/components/ui/button.tsx'
rg -nB1 -A2 '<Button[^>]*onClick' "$SCOPE" --glob '!**/components/ui/**' \
  | rg -B1 -A2 -v 'DropdownMenu|Popover|Command|Combobox'
rg -n 'from-violet-[0-9]+\s+to-blue-[0-9]+' "$SCOPE" --glob '!**/components/ui/buttons/**'
rg -nB0 -A0 '<button[^>]*bg-primary|<Button[^>]*bg-primary' "$SCOPE"
rg -n '<Button[^>]*type=["\x27]submit' "$SCOPE" --glob '!**/components/ui/**'
```

## Avatars

```bash
rg -n '<img[^>]*(src=\{[^}]*[Aa]vatar|src=\{[^}]*\.avatar|cdn\.discordapp)' "$SCOPE"
rg -n 'AvatarUrl\s*\(' "$SCOPE" --glob '!**/UserAvatar*'
```

## Breadcrumbs

```bash
rg -nB0 -A2 '<nav[^>]*>' "$SCOPE/routes/(organizations|leagues|events|event-series|tournament|rollcall)/"
rg -n '<Breadcrumb\b' "$SCOPE/routes/(organizations|leagues|events|event-series|tournament|rollcall)/"
```

## Selects

```bash
# Bare shadcn Select primitive in a user-facing picker (should use BrandSelect family)
rg -n "from '~/components/ui/select'" "$SCOPE" \
  --glob '!**/components/ui/select.tsx' \
  --glob '!**/components/ui/brand-select.tsx'

# Hand-rolled color override on a SelectTrigger
rg -n '<SelectTrigger[^>]*className="[^"]*\b(bg-(slate|gray|zinc|neutral|stone)-|text-(black|white)\b)' "$SCOPE"
```

## Tokens vs Literals

```bash
rg -n 'bg-violet-[0-9]+|bg-indigo-[0-9]+|text-violet-[0-9]+' "$SCOPE" \
  --glob '!**/components/ui/buttons/**' --glob '!**/app.css'
rg -n 'bg-slate-[0-9]+|border-slate-[0-9]+' "$SCOPE" \
  --glob '!**/components/ui/**' --glob '!**/app.css' --glob '!**/tailwind.config.js'
rg -n 'text-(gray|slate|zinc)-[0-9]+' "$SCOPE" \
  --glob '!**/components/ui/**' --glob '!**/app.css'
rg -n 'bg-\[#|text-\[#|border-\[#|ring-\[#' "$SCOPE"
rg -n '\[oklch\(' "$SCOPE"
rg -n 'from-violet-500\s+to-blue-500' "$SCOPE" --glob '!**/components/ui/buttons/styles.ts'
```

## Inline styles

```bash
rg -n 'style=\{\{' "$SCOPE"
rg -n 'shadow-\[0[ _]0[ _]' "$SCOPE" --glob '!**/components/ui/buttons/**'
rg -n 'space-[xy]-' "$SCOPE"
rg -nP 'w-(\d+)\s+h-\1\b' "$SCOPE"
rg -n 'className=\{`[^`]*\$\{[^}]+\?' "$SCOPE"
```

## Dialogs

```bash
# DialogContent with bg-gradient override (will strip bg-background)
rg -nB0 -A2 'DialogContent[^>]*bg-gradient' "$SCOPE"
rg -nB0 -A2 'AlertDialogContent[^>]*bg-gradient' "$SCOPE"

# <Dialog> / <AlertDialog> missing Title (manual review per hit)
for primitive in DialogContent AlertDialogContent; do
  rg -nB0 -A20 "<$primitive" "$SCOPE" \
    | rg -B1 -A20 "<$primitive" \
    | rg -L "${primitive%Content}Title"
done

# Form-heavy DialogContent without a max-w override (too narrow for multi-field forms)
rg -nB0 -A2 '<DialogContent' "$SCOPE" | rg -L 'max-w-'

# Raw overflow-y-auto inside DialogContent — should be <ScrollArea>
rg -nB0 -A8 '<DialogContent' "$SCOPE" | rg -B1 -A2 'overflow-y-auto'

# <ScrollArea> child but no overflow-hidden — Radix Viewport never enables scrollbar
rg -nB0 -A12 '<DialogContent' "$SCOPE" \
  | rg -B12 'ScrollArea' \
  | rg -L 'overflow-hidden'
```

### Confirmation dialogs — anti-patterns

Every match below is a `block` finding.

```bash
# <AlertDialog> outside the canonical wrapper
rg '<AlertDialog\b' frontend/app -g '*.tsx' -g '*.ts' --glob '!**/components/ui/dialogs/**'

# window.confirm() in any .tsx/.ts
rg 'window\.confirm\(' frontend/app -g '*.tsx' -g '*.ts'

# <AlertDialogAction> / <AlertDialogCancel> outside components/ui/
rg '<AlertDialogAction\b|<AlertDialogCancel\b' frontend/app -g '*.tsx' --glob '!**/components/ui/**'

# Hand-rolled name-match destructive input (should use <DeleteDialog>)
rg '=== \w+\.name' frontend/app -g '*.tsx' --glob '!**/components/ui/dialogs/**'
```

## Keyboard hints

```bash
rg -n '<kbd[\s>]' "$SCOPE" --glob '!**/components/ui/kbd.tsx'
rg -nB1 -A4 '<(Primary|Secondary|Destructive|Confirm|Cancel)Button\b' "$SCOPE" \
  --glob '!**/components/ui/buttons/**' | rg -B4 -A1 '<Kbd\b'
```

## Component placement

```bash
fd -e tsx -e ts . "$SCOPE" | rg -v '/components/ui/' \
  | xargs -I{} rg -l '"@radix-ui/' {} 2>/dev/null
fd -g 'Button*.tsx' "$SCOPE" --exclude '**/components/ui/buttons/**'
```

## Smoke check

```bash
rg -n '<button[^>]*onClick|bg-violet-|bg-slate-[0-9]|<img[^>]*[Aa]vatar|style=\{\{|window\.confirm\(' \
  frontend/app --glob '!**/components/ui/**'
```
