# Grep Recipes

Copy-paste `rg` recipes for finding brand violations across the [in-scope](scope.md) tree. Run from the draftforge repo root.

## Define the scope once

```bash
SCOPE=frontend/app
```

Most recipes glob `--glob '!**/components/ui/**'` to skip the bare shadcn primitives (those are out of scope for this skill).

## Buttons

```bash
# Raw <button> outside the brand button library
rg -n '<button[^>]*onClick' "$SCOPE" --glob '!**/components/ui/buttons/**' --glob '!**/components/ui/button.tsx'

# Raw <Button onClick> for domain actions (allowed only for triggers)
# Reviewer must inspect each hit in context — flag any with a domain handler
rg -nB1 -A2 '<Button[^>]*onClick' "$SCOPE" \
  --glob '!**/components/ui/**' \
  | rg -B1 -A2 -v 'DropdownMenu|Popover|Command|Combobox'

# Custom violet/blue gradient buttons (should use <PrimaryButton>)
rg -n 'from-violet-[0-9]+\s+to-blue-[0-9]+' "$SCOPE" --glob '!**/components/ui/buttons/**'

# bg-primary on a button (button uses gradient, not flat)
rg -nB0 -A0 '<button[^>]*bg-primary|<Button[^>]*bg-primary' "$SCOPE"

# Form submit using <Button type="submit"> instead of <SubmitButton>
rg -n '<Button[^>]*type=["\x27]submit' "$SCOPE" --glob '!**/components/ui/**'
```

## Avatars

```bash
# Raw <img> for avatars
rg -n '<img[^>]*(src=\{[^}]*[Aa]vatar|src=\{[^}]*\.avatar|cdn\.discordapp)' "$SCOPE"

# Direct AvatarUrl() calls in JSX (must go through <UserAvatar>)
rg -n 'AvatarUrl\s*\(' "$SCOPE" --glob '!**/UserAvatar*'
```

## Breadcrumbs

```bash
# Hand-built breadcrumb nav on detail routes
rg -nB0 -A2 '<nav[^>]*>' "$SCOPE/routes/(organizations|leagues|events|event-series|tournament|rollcall)/"

# Plain shadcn <Breadcrumb> on routes that should use <EntityBreadcrumb>
rg -n '<Breadcrumb\b' "$SCOPE/routes/(organizations|leagues|events|event-series|tournament|rollcall)/"
```

## Tokens vs Literals

```bash
# Raw violet/indigo classes (should be <PrimaryButton> / <SecondaryButton> / brand constants)
rg -n 'bg-violet-[0-9]+|bg-indigo-[0-9]+|text-violet-[0-9]+' "$SCOPE" \
  --glob '!**/components/ui/buttons/**' --glob '!**/app.css'

# Raw slate classes for surfaces (should be bg-base-*)
rg -n 'bg-slate-[0-9]+|border-slate-[0-9]+' "$SCOPE" \
  --glob '!**/components/ui/**' --glob '!**/app.css' --glob '!**/tailwind.config.js'

# Raw gray text classes (should be text-foreground / text-muted-foreground)
rg -n 'text-(gray|slate|zinc)-[0-9]+' "$SCOPE" \
  --glob '!**/components/ui/**' --glob '!**/app.css'

# Hardcoded hex in className
rg -n 'bg-\[#|text-\[#|border-\[#|ring-\[#' "$SCOPE"

# Hardcoded oklch in className
rg -n '\[oklch\(' "$SCOPE"

# Hand-rolled brand gradient (should import brandGradient)
rg -n 'from-violet-500\s+to-blue-500' "$SCOPE" \
  --glob '!**/components/ui/buttons/styles.ts'
```

## Inline styles

```bash
# style={{...}} — review each hit; dynamic values are OK
rg -n 'style=\{\{' "$SCOPE"

# Hand-rolled box-shadow
rg -n 'shadow-\[0[ _]0[ _]' "$SCOPE" --glob '!**/components/ui/buttons/**'

# space-x-* / space-y-*
rg -n 'space-[xy]-' "$SCOPE"

# w-N h-N pairs (should be size-N)
rg -nP 'w-(\d+)\s+h-\1\b' "$SCOPE"

# Template-literal conditional classNames (should use cn())
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

# Hand-rolled <AlertDialog> confirm flows (should be <ConfirmDialog>)
# Manual review: any AlertDialog whose body is just title/desc/yes-no buttons
# is a candidate for ConfirmDialog (which adds Enter/Backspace + <Kbd> hints).
rg -n '<AlertDialog\b' "$SCOPE" --glob '!**/components/ui/**'

# Form-heavy DialogContent without a max-w override (defaults to sm:max-w-lg,
# too narrow for multi-section forms). Manual review per hit: confirm dialogs
# keep the default; edit/signup/create modals should be sm:max-w-2xl.
# See THEMING-GUIDE.md §"Dialog Widths".
rg -nB0 -A2 '<DialogContent' "$SCOPE" | rg -L 'max-w-'

# Raw overflow-y-auto inside DialogContent — should be <ScrollArea> for
# the brand-styled scrollbar. The OS-default scrollbar inside a themed
# dialog reads as visual drift. See THEMING-GUIDE.md §"Dialog Widths".
rg -nB0 -A8 '<DialogContent' "$SCOPE" | rg -B1 -A2 'overflow-y-auto'

# DialogContent with a <ScrollArea> child but no overflow-hidden — the
# dialog won't clip, ScrollArea Root has no definite height, Radix Viewport
# never enables its scrollbar. See scrollbars-dialogs.md for the full chain.
# Block-severity finding (PR #220 broke a Playwright spec because of this).
rg -nB0 -A12 '<DialogContent' "$SCOPE" \
  | rg -B12 'ScrollArea' \
  | rg -L 'overflow-hidden'
```

## Keyboard hints

```bash
# Raw <kbd> elements — should be <Kbd> from ~/components/ui/kbd
rg -n '<kbd[\s>]' "$SCOPE" --glob '!**/components/ui/kbd.tsx'

# <Kbd> rendered as a child of a brand button — should be the `hotkey` prop
# instead so the standardized HotkeyBadge (corner pill + LazyTooltip) is used.
rg -nB1 -A4 '<(Primary|Secondary|Destructive|Confirm|Cancel)Button\b' "$SCOPE" \
  --glob '!**/components/ui/buttons/**' \
  | rg -B4 -A1 '<Kbd\b'
```

## Component placement

```bash
# New shadcn primitives added outside the canonical components/ui/ tree
fd -e tsx -e ts . "$SCOPE" \
  | rg -v '/components/ui/' \
  | xargs -I{} rg -l '"@radix-ui/' {} 2>/dev/null

# Buttons added outside buttons/ folder convention
fd -g 'Button*.tsx' "$SCOPE" --exclude '**/components/ui/buttons/**'
```

## Putting it together

A quick smoke check before opening a PR:

```bash
# Run all the high-signal recipes in one shot
rg -n '<button[^>]*onClick|bg-violet-|bg-slate-[0-9]|<img[^>]*[Aa]vatar|style=\{\{' frontend/app \
  --glob '!**/components/ui/**'
```
