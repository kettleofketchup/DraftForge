# Review Checklist

Walk this list against any diff that touches an [in-scope source tree](scope.md). Every violation cites `file:line` and a section of `THEMING-GUIDE.md` for the *why*.

## 1. Brand Button Wrappers

- [ ] No raw `<button>` with hand-rolled Tailwind. Use the matching brand wrapper. → [substitutions](component-substitutions.md)
- [ ] No raw `<Button>` (from `~/components/ui/button`) with an `onClick` for a domain action. Reserve raw `<Button>` for dropdown / popover / combobox triggers and shadcn internals.
- [ ] Form submission uses `<SubmitButton>`, not `<Button type="submit">`.
- [ ] Dialog confirmation uses `<ConfirmButton variant="...">`, not `<PrimaryButton>` / `<DestructiveButton>`.
- [ ] Page-level destructive action uses `<DestructiveButton>`, not `<ConfirmButton variant="destructive">`.
- [ ] Edit affordance uses `<EditButton>` / `<EditIconButton>`, not a custom violet button.
- [ ] Icon-only buttons live in `frontend/app/components/ui/buttons/icons/` (not invented inline).

## 2. Mandatory Components

- [ ] `<UserAvatar>` for every avatar render. No raw `<img>` with `AvatarUrl()`. → [substitutions](component-substitutions.md#avatars)
- [ ] `<EntityBreadcrumb>` on every detail page that requires it (organization, league, event, event-series, tournament, rollcall). → [substitutions](component-substitutions.md#breadcrumbs)
- [ ] No hand-built breadcrumb `<nav>` markup on those pages.

## 3. Tokens vs Literals

- [ ] No `bg-violet-*` / `bg-indigo-*` for buttons — use `<PrimaryButton>` / `<SecondaryButton>` / `brandGradient`. → [inline-styles](inline-styles.md)
- [ ] No `bg-slate-*` for surfaces — use `bg-base-*`.
- [ ] No `text-slate-100` / `text-gray-*` — use `text-foreground`, `text-text-secondary`, `text-muted-foreground`.
- [ ] Status colors use semantic tokens: `text-success` / `text-warning` / `text-error` / `text-info`.
- [ ] No hand-rolled gradients matching the brand — import the constant from `~/components/ui/buttons/styles`.
- [ ] No hex / oklch literals in `className` (`bg-[#...]`, `text-[#...]`). Exception: `[background-image:var(--brand-bg)]` arbitrary property on dialog surfaces.

## 4. Inline Styles

- [ ] No `style={{}}` for static styling. Dynamic computed values only. → [inline-styles](inline-styles.md)
- [ ] No `space-x-*` / `space-y-*`. Use `flex gap-*`.
- [ ] `size-*` for equal width/height, not `w-N h-N`.
- [ ] Conditional classes use `cn()`, not template-literal ternaries.

## 5. Glow / Effects

- [ ] Glow effects pull from utility classes (`text-glow-violet`, `text-glow-cyan`, `border-glow`, `glow-hover`, `gradient-glow-*`) or from `brandGlow` / `shadow-brand-glow`. Not hand-rolled `shadow-[...]`.
- [ ] `gradient-button` / `gradient-button-glow` for button gradient variants.
- [ ] `gradient-bg-subtle` / `gradient-hero` for page surface gradients.

## 6. Dialog Surfaces

- [ ] `<Dialog>` / `<AlertDialog>` content does NOT add `bg-gradient-to-*` overrides — `brandBg` is automatic and tailwind-merge will strip `bg-background`. → [substitutions](component-substitutions.md#dialogs)
- [ ] Custom dialog overlays use the arbitrary property `[background-image:var(--brand-bg)]`, not `bg-gradient-*`.
- [ ] `<Dialog>` / `<AlertDialog>` always include `<DialogTitle>` / `<AlertDialogTitle>` (use `className="sr-only"` if visually hidden).
- [ ] Confirmation flows use canonical wrappers from `~/components/ui/dialogs`:
  - Yes/no confirm (positive OR negative) → `<ConfirmDialog>` with the appropriate `variant`.
  - Destructive with a typed-name gate (League, Organization, Event Series) → `<DeleteDialog>` with `entityKind` + `entityName`.
  Never hand-roll `<AlertDialog>` for these. Never `window.confirm()` in `.tsx`/`.ts`.
- [ ] Keyboard hints use `<Kbd>` from `~/components/ui/kbd`, never raw `<kbd>`.
- [ ] Brand buttons exposing a page-level shortcut use the `hotkey` prop, never a hand-rolled `<Kbd>` child. The prop renders `<HotkeyBadge>` (corner pill + LazyTooltip) — bypassing it skips the tooltip and breaks the standardized pattern.

## 7. Component Placement

- [ ] Generic, shape-agnostic buttons live at root of `buttons/`.
- [ ] Icon-only variants live in `buttons/icons/`.
- [ ] Domain-specific buttons (Steam, Dotabuff, Discord, etc.) live in `buttons/<domain>/`.
- [ ] Page-specific buttons used in only one feature are co-located in the feature folder, NOT in `buttons/`.
- [ ] No new files under `frontend/app/components/ui/buttons/` without a barrel update in `index.ts`.

## 8. Accessibility

- [ ] Every interactive `<div>` / `<span>` with `onClick` also has keyboard support — usually means it should be a button.
- [ ] Icon-only buttons have `aria-label`.
- [ ] Decorative icons inside text-bearing buttons have `aria-hidden`.
- [ ] Forms use shadcn `<Form>` + `<FormField>` (not raw `<input>` + manual labels).
- [ ] Error messages render in `text-error` / `text-destructive` AND with text content (not color-only).
