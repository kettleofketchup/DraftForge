# Component Substitutions

Replace hand-rolled HTML and one-off styled markup with DraftForge's brand component wrappers. The wrappers ship the brand gradient, 3D depth, hover/active states, focus rings, and disabled treatment; raw markup loses all of it and drifts visually over time.

## Buttons (Primary Targets)

Per [`THEMING-GUIDE.md` §"Button Policy"](../../THEMING-GUIDE.md#button-policy): all user-facing actions use a brand button wrapper from `~/components/ui/buttons`. Raw `<Button>` is reserved for structural uses only.

| Anti-pattern | Replace with | Notes |
|---|---|---|
| `<button onClick={...}>...` | `<PrimaryButton onClick={...}>` | Brand violet→blue gradient + 3D depth. The headline CTA on a view. |
| `<button className="bg-primary ...">` | `<PrimaryButton>` | `bg-primary` flat is reserved for non-button contexts. Buttons use the gradient. |
| `<Button onClick={submit}>Save</Button>` (form submission) | `<SubmitButton loading={isSubmitting}>Save</SubmitButton>` | Wires `type="submit"` + loading spinner. |
| `<Button>Confirm</Button>` inside a dialog | `<ConfirmButton variant="success">Approve</ConfirmButton>` | Pairs with `variant="destructive"` / `variant="warning"` for the matching dialog tone. |
| Supporting / contextual action | `<SecondaryButton>` | Violet gradient + ring outline. "Cancel", "Edit Settings", etc. |
| Cancel / dismiss inside a dialog | `<CancelButton>` or `<SecondaryButton>` | Translucent violet on opaque backgrounds. |
| Edit affordance | `<EditButton>` / `<EditIconButton>` | Toxic violet→emerald cyberpunk blend per `brandToxic`. |
| Destructive page-level action | `<DestructiveButton>` | Red + 3D. NOT for dialog confirmation — use `<ConfirmButton variant="destructive">` there. |
| Navigation action (link styled as button) | `<NavButton>` | Sky blue + 3D. |
| Icon-only variant of a generic button | The matching `*IconButton` in `buttons/icons/` (e.g. `<EditIconButton>`, `<ViewIconButton>`) | Don't roll a new icon-only button — extend the icons folder. |

### Structural `<Button>` exceptions (NOT a violation)

Raw `<Button>` from `~/components/ui/button` is **correct** in these contexts:

- `<DropdownMenuTrigger asChild><Button>...</Button></DropdownMenuTrigger>`
- `<PopoverTrigger asChild><Button>...</Button></PopoverTrigger>`
- `<Command>` / `<Combobox>` triggers
- shadcn primitive internals (e.g. inside `dialog.tsx` itself)

If `<Button>` has an `onClick` that performs a domain action (save, delete, navigate), that's a `block` regardless of where it sits.

## Avatars

| Anti-pattern | Replace with | Notes |
|---|---|---|
| `<img src={user.avatar} ...>` | `<UserAvatar user={user} size="md" />` | Handles Discord CDN, fallback initials, memoization. |
| `<img src={AvatarUrl(user)} ...>` | `<UserAvatar user={user} size="md" />` | `AvatarUrl()` is wrapped — never call it directly in JSX. |
| Custom online-indicator dot | `<UserAvatar user={user} showOnline online />` | The component renders the indicator. |
| Custom captain ring | `<UserAvatar user={user} border="captain" />` | Gold ring is built in. |

Sizes: `tiny` (16px) | `xs` (20px) | `sm` (24px) | `md` (32px) | `lg` (40px) | `xl` (48px). Don't invent intermediate sizes.

## Breadcrumbs

| Anti-pattern | Replace with | Notes |
|---|---|---|
| Hand-built `<nav><a>...</a></nav>` breadcrumb | `<EntityBreadcrumb segments={[...]} />` | Renders typed segment labels above each name. |
| Plain shadcn `<Breadcrumb>` on a detail page | `<EntityBreadcrumb>` | The shadcn primitive is for non-entity contexts (settings, etc.). Detail pages MUST use `EntityBreadcrumb`. |

Required breadcrumb pages: `/organizations/:id`, `/leagues/:id`, `/events/:id`, `/event-series/:id`, `/tournament/:pk`, `/rollcall/:eventId`. Missing breadcrumb on a required page = `block`.

## Dialogs

| Anti-pattern | Replace with | Notes |
|---|---|---|
| Custom `<div role="dialog">` | shadcn `<Dialog>` / `<AlertDialog>` | Brand surface (`brandBg`) is automatic. |
| `<DialogContent className="bg-gradient-to-r ...">` | Don't override the surface | Tailwind-merge will strip `bg-background` and the dialog goes translucent. Use `[background-image:var(--brand-bg)]` arbitrary property if a custom overlay is genuinely needed. |
| `<Dialog>` without `<DialogTitle>` | Always include title | Use `className="sr-only"` if visually hidden — required for a11y. |
| Hand-rolled `<AlertDialog>` for any yes/no confirm — positive ("add user", "approve", "pick hero") OR negative ("delete", "restart") | `<ConfirmDialog>` from `~/components/ui/dialogs`. Auto-wires Enter/Backspace + brand button variants + variant-aware destructive/warning surfaces. |
| Hand-rolled name-match destructive flow (input "Type the X name to confirm" gating a delete) | `<DeleteDialog>` from `~/components/ui/dialogs`. Pass `entityKind` + `entityName`; the dialog inherits the destructive surface and gates Delete on strict equality. |

## Keyboard Hints

| Anti-pattern | Replace with | Notes |
|---|---|---|
| `<kbd>Enter</kbd>` raw | `<Kbd>Enter</Kbd>` from `~/components/ui/kbd` | Brand keycap styling (mono background, rounded). Raw `<kbd>` inherits browser defaults. Reserve direct `<Kbd>` use for *prose* (docs, help panes) and tooltip bodies — for buttons, use the `hotkey` prop below. |
| Inline keyboard hint without `<Kbd>` (e.g. `(press Enter)` plain text) | Wrap the symbol/key name in `<Kbd>` | Keeps the visual rhythm with hotkey-aware surfaces. |
| Brand button (`<PrimaryButton>` / `<SecondaryButton>` / `<DestructiveButton>` / `<ConfirmButton>` / `<CancelButton>`) with a hand-rolled `<Kbd>` child for a shortcut | Pass the `hotkey` prop instead | The brand button renders `<HotkeyBadge>` (a `<Kbd>` anchored top-left as a corner pill, plus a `LazyTooltip` saying "Press X for keyboard shortcut") and adds `relative` for you. Inline `<Kbd>` next to the label is a `block` review finding because it skips the tooltip + breaks the standardized corner-pill pattern. |
| `<ConfirmDialog>` confirm/cancel buttons rendered with inline keyboard hints | The dialog already wires `hotkey="↵"` / `hotkey="⌫"` for you | Use `<ConfirmDialog>` directly — never re-implement Enter/Backspace + corner badges by hand. |
| `<FormLabel>` with a hand-rolled `<Kbd>` keycap next to the label text | Pass the `hotkey` prop on `<FormLabel>` | `<FormLabel hotkey="N">Nickname</FormLabel>` renders the Kbd inline for you and applies the right flex layout. Wire the actual focus handler in the parent (e.g. modal `useEffect` listening for the matching `keydown`). |

## Status / Win-Loss Indicators

| Anti-pattern | Replace with | Notes |
|---|---|---|
| `<span className="text-green-500">WIN</span>` | `<span className="text-success">WIN</span>` | Use the semantic token. |
| `<span style={{ color: '#ef4444' }}>LOSS</span>` | `<span className="text-error">LOSS</span>` | rose-500 token. |
| Custom ranking badge | `<Badge className="bg-warning text-warning-foreground">1st</Badge>` | shadcn `Badge` + status tokens. |
