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

Inline `style={{}}` is acceptable **only** for dynamic computed values: a progress bar's `width: ${pct}%`, a positioned floating overlay, or a CSS variable injected from props (`style={{ '--row-h': `${rowH}px` }}`). Static styling MUST be Tailwind.

The one **sanctioned exception** for dialog surfaces is the `[background-image:var(--brand-bg)]` arbitrary property — see [`THEMING-GUIDE.md` §"Brand Surface Background"](../../THEMING-GUIDE.md#brand-surface-background-brandbg). That's not inline style; it's a Tailwind arbitrary property and is the *only* correct way to layer a gradient over `bg-background`.

### Raw violet/indigo Tailwind classes

```tsx
// WRONG — bypasses brand tokens
<button className="bg-violet-500 text-white">

// RIGHT — use a brand wrapper
<PrimaryButton>...</PrimaryButton>

// or for non-button contexts
<span className="text-primary">...</span>
<div className="bg-secondary">...</div>
```

The brand primary is a **gradient**, not a flat violet. If you find yourself reaching for `bg-violet-*` you almost certainly want `<PrimaryButton>` or `brandGradient` (imported from `~/components/ui/buttons/styles`).

### Raw slate classes instead of `bg-base-*`

```tsx
// WRONG
<div className="bg-slate-900">
<div className="bg-slate-800 border border-slate-700">

// RIGHT — use the base scale
<div className="bg-base-900">
<div className="bg-base-800 border border-border">
```

The `bg-base-*` scale maps slate values to a semantic elevation hierarchy (lower number = brighter / more elevated). Raw slate classes break this contract and make future palette tweaks painful.

See [`THEMING-GUIDE.md` §"Background Scale (Slate)"](../../THEMING-GUIDE.md#background-scale-slate).

### Hand-rolled gradients

```tsx
// WRONG
<button className="bg-gradient-to-r from-violet-500 to-blue-500 hover:from-violet-400 hover:to-blue-400 text-white">

// RIGHT — import the constant
import { brandGradient } from '~/components/ui/buttons/styles';
<button className={brandGradient}>
// (or just use <PrimaryButton>)
```

`brandGradient`, `brandSecondary`, `brandErrorBg`, `brandErrorCard`, `brandSuccessBg`, `brandSecondaryOpaque`, `brandBg`, `brandGlow`, `brandToxic`, `brandToxicDepthColors` — all exported from `~/components/ui/buttons` (and `styles.ts`). Hand-rolling these is a `block` because the constants drift independently and reviewers can't easily diff them.

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

Hex/oklch literals in `className` are review blocks. The `[bg-image:var(--brand-bg)]` arbitrary property is the **only** sanctioned arbitrary value, and only on dialog surfaces.

### `space-x-*` / `space-y-*`

```tsx
// WRONG
<div className="space-y-4">

// RIGHT
<div className="flex flex-col gap-4">
```

Use `flex` + `gap-*`. `space-*` doesn't honor RTL and breaks with conditional children.

### `w-N h-N` for square dimensions

```tsx
// WRONG
<Avatar className="w-10 h-10">

// RIGHT
<Avatar className="size-10">
// or just use <UserAvatar size="lg">
```

### Conditional classes without `cn()`

```tsx
// WRONG
className={`base-class ${active ? 'extra' : ''}`}

// RIGHT
import { cn } from '~/lib/utils';
className={cn('base-class', active && 'extra')}
```

`cn()` (clsx + tailwind-merge) deduplicates conflicting classes — critical when composing brand constants with caller-supplied `className` overrides.

### Ad-hoc glow / shadow

```tsx
// WRONG
<div className="shadow-[0_0_10px_rgba(139,92,246,0.5)]">

// RIGHT — use the brand glow tokens
import { brandGlow } from '~/components/ui/buttons/styles';
<div className={brandGlow}>
// or the utility class
<div className="shadow-brand-glow">
```

For text glow, use `text-glow`, `text-glow-violet`, `text-glow-cyan`. For radial backgrounds, use `gradient-glow-violet` / `gradient-glow-cyan`. These all live in `app.css`.

## What's NOT an inline-style violation

- `style={{ width: `${pct}%` }}` for a computed progress bar.
- `style={{ '--row-h': `${rowH}px` }}` to feed a value into a CSS variable consumed by Tailwind utilities.
- The arbitrary property `[background-image:var(--brand-bg)]` on dialog surfaces (sanctioned by `THEMING-GUIDE.md`).
- `dangerouslySetInnerHTML` for sanitized content (separate concern).

The rule: **static style → className with tokens**; dynamic numeric value → `style={{}}` is fine.
