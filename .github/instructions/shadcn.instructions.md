---
applyTo: "frontend/app/components/**/*.{ts,tsx}"
---

# shadcn/ui composition

Canonical: global `shadcn` skill. Project config lives in `frontend/components.json`; primitives live in `frontend/app/components/ui/`.

## Compose, don't reinvent

- **Use existing shadcn primitives from `frontend/app/components/ui/` first.** A "settings page" composes `Tabs` + `Card` + form controls; a "dashboard" composes `Sidebar` + `Card` + `Table` / `Chart`. Don't hand-roll alternatives.
- **Use built-in variants before custom styling.** `variant="outline"`, `size="sm"`, etc. — defined on each shadcn component.

## Styling — what `className` may and may not do

- **`className` is for layout, not styling.** Override layout (positioning, margins, sizing) but never override component colors, typography, or border radius — those come from the design tokens.
- **No manual `dark:` colour overrides.** Use semantic tokens (`bg-background`, `text-foreground`, `text-muted-foreground`, `border-input`) so dark mode flips automatically.
- **No manual `z-index` on overlay components.** `Dialog`, `Sheet`, `Popover`, `DropdownMenu`, `Tooltip`, `Toast` manage their own stacking — overriding breaks the stack.

## Forms (interacts with brand and `zod-form-validation`)

- **`FieldGroup` + `Field` for form layout** — never raw `div` with `space-y-*` or `grid gap-*`.
- **Inside `InputGroup`, use `InputGroupInput` / `InputGroupTextarea`** — never raw `Input` / `Textarea`.
- **Option sets of 2–7 choices use `ToggleGroup`** — don't loop `Button` with manual active state.
- **`FieldSet` + `FieldLegend` for groups of related checkboxes / radios** — not a `div` with a heading.
- **Validation: `data-invalid` on `Field`, `aria-invalid` on the control.** For disabled: `data-disabled` on `Field`, `disabled` on the control.

## Interactions with the brand skill

When `frontend/app/components/ui/buttons/` is involved, brand rules win — use `PrimaryButton` / `SecondaryButton` / `ConfirmButton` / `EditButton` rather than raw shadcn `Button`. shadcn `Button` is the underlying primitive but should not be reached for directly in product UI.
