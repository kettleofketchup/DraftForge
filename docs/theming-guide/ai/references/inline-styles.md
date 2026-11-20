# Inline Styles & Hardcoded Values

DraftForge's brand is enforced through semantic tokens (`bg-primary`, `bg-base-900`, `text-foreground`, `text-success`). Inline styles, raw Tailwind colors (`bg-violet-500`, `bg-slate-900`), and hardcoded gradients bypass the token layer and drift over time. Block these in review.

## Anti-patterns and Fixes

### `style={{ ... }}` for static styling

```tsx
// WRONG
<div style={{ background: '#020617', padding: '16px' }}>

// RIGHT
<div className="bg-base-950 p-4">
```

Acceptable only for dynamic computed values (`width: ${pct}%`, CSS variable injection). Static styling MUST be Tailwind. Exception: `[background-image:var(--brand-bg)]` on dialog surfaces (see [`THEMING-GUIDE.md` §"Brand Surface Background"](../../../THEMING-GUIDE.md#brand-surface-background-brandbg)).

### Raw violet/indigo Tailwind classes

```tsx
// WRONG
<button className="bg-violet-500 text-white">
// RIGHT
<PrimaryButton>...</PrimaryButton>
```

The brand primary is a gradient — use `<PrimaryButton>` or import `brandGradient` from `~/components/ui/buttons/styles`.

### Raw slate classes instead of `bg-base-*`

```tsx
// WRONG
<div className="bg-slate-900">
<div className="bg-slate-800 border border-slate-700">

// RIGHT — use the base scale
<div className="bg-base-900">
<div className="bg-base-800 border border-border">
```

See [`THEMING-GUIDE.md` §"Background Scale (Slate)"](../../../THEMING-GUIDE.md#background-scale-slate).

### Raw palette classes for a fixed meaning

```tsx
// WRONG
<span className={team === 'radiant' ? 'text-green-400' : 'text-red-400'}>
// RIGHT
<span className={team === 'radiant' ? 'text-radiant' : 'text-dire'}>
```

Team sides, pick/ban, the acting turn, draft styles, positions, roles, rank status,
placings, presence, GPM/XPM and Discord each have a domain token. Choose by meaning, not
by the lint's nearest-shade hint. See [`THEMING-GUIDE.md` §"Domain Colors"](../../../THEMING-GUIDE.md#domain-colors).

### Hand-rolled gradients

```tsx
// WRONG
<button className="bg-gradient-to-r from-violet-500 to-blue-500 hover:from-violet-400 hover:to-blue-400 text-white">

// RIGHT — import the constant
import { brandGradient } from '~/components/ui/buttons/styles';
<button className={brandGradient}>
// (or just use <PrimaryButton>)
```

`brandGradient`, `brandSecondary`, `brandErrorBg`, `brandSuccessBg`, `brandBg`, `brandGlow`, `brandToxic` — all exported from `~/components/ui/buttons`. Hand-rolling is a `block`.

### Hardcoded hex / oklch in `className`

```tsx
// WRONG
<div className="bg-[#020617]">
<div className="text-[#7c3aed]">
<div className="ring-[oklch(0.541_0.251_293)]">

// RIGHT — use semantic tokens
<div className="bg-base-950">
<div className="text-primary">
<div className="ring-ring">
```

Hex/oklch literals in `className` are `block`. The `[bg-image:var(--brand-bg)]` arbitrary property is the only sanctioned arbitrary value, and only on dialog surfaces.

### `space-x-*` / `space-y-*`

Use `flex` + `gap-*` instead. `space-*` doesn't honor RTL and breaks with conditional children.

### `w-N h-N` for square dimensions

Use `size-N` (or `<UserAvatar size="lg">`).

### Conditional classes without `cn()`

Use `cn()` (clsx + tailwind-merge) from `~/lib/utils` — deduplicates conflicting classes when composing brand constants.

### Ad-hoc glow / shadow

Use `brandGlow` / `shadow-brand-glow`. Text glow: `text-glow-violet`, `text-glow-cyan`. Radial: `gradient-glow-violet` / `gradient-glow-cyan` (all in `app.css`).

### Body text on a colored brand surface

Use the variant-matched readable constant — not `text-muted-foreground` (fades) and never a `text-shadow` outline on body copy (`block`).

| Constant | Use over |
|---|---|
| `brandReadableSuccess` | `brandSuccessBg`, emerald gradients |
| `brandReadableWarning` | warning surfaces, orange/amber gradients |
| `brandReadableDestructive` | destructive surfaces, red gradients |

For display/title text use `text-outline-black`. All exported from `~/components/ui/buttons`.

### Inner panels on a colored dialog surface

Use `brandDialogPanel` (`bg-black/40 ring-1 ring-white/10`) for any nested block (UserStrip, info cards, recap rows) rendered inside a colored brand dialog.

```tsx
import { brandDialogPanel } from '~/components/ui/buttons';
<UserStrip user={user} showBorder={false} className={brandDialogPanel} />
```

## Destructive dialog surface

`ConfirmDialog`'s destructive surface is `bg-error-surface/95 border-error/40`;
`<DeleteDialog>` inherits it. There is no sanctioned raw `bg-red-*` anymore: use
`bg-destructive` / `border-destructive` / `ring-destructive` for the destructive intent,
`bg-error-surface` for opaque error fills, and `bg-base-900/80` for recessed surfaces
inside the destructive dialog (see `DeleteDialog`'s Input).

## What's NOT an inline-style violation

- `style={{ width: `${pct}%` }}` for a computed progress bar.
- `style={{ '--row-h': `${rowH}px` }}` to feed a value into a CSS variable consumed by Tailwind utilities.
- The arbitrary property `[background-image:var(--brand-bg)]` on dialog surfaces (sanctioned by `THEMING-GUIDE.md`).
- `dangerouslySetInnerHTML` for sanitized content (separate concern).

The rule: **static style → className with tokens**; dynamic numeric value → `style={{}}` is fine.
