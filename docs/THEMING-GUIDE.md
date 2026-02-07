# DraftForge Theming Guide

## Theme Overview

**Visual Vibe**: Neon Cyber Esports | Dota-style Draft UI | Dark Mode First

This theme uses a violet/indigo primary palette with cyan accents for an esports-focused, competitive gaming aesthetic.

**Location**: `frontend/app/app.css`

---

## Color Palette

### Primary (Brand) - Violet-to-Blue Gradient

| Token | Tailwind Classes | Usage |
|-------|-----------------|-------|
| `--primary` | `bg-primary` (violet-400 dark) | Base brand color: focus rings, links, badges |
| `brandGradient` | `bg-gradient-to-r from-violet-500 to-blue-500 hover:from-violet-400 hover:to-blue-400 text-white` | Primary CTA buttons |
| `brandSecondary` | `bg-gradient-to-r from-violet-500/30 to-blue-500/20 ring-1 ring-violet-300/60 text-violet-100 hover:from-violet-500/40 hover:to-blue-500/30` | Supporting/contextual actions |

Primary CTA buttons use the brand gradient via `<PrimaryButton>`, not flat `bg-primary`. The `--primary` CSS variable remains the base brand color for non-button contexts.

```tsx
// Primary CTA (brand gradient + 3D depth)
<PrimaryButton>Create Tournament</PrimaryButton>
<PrimaryButton depth={false}>Flat Variant</PrimaryButton>

// Secondary brand action (violet gradient + ring outline)
<SecondaryButton>Edit Settings</SecondaryButton>
```

### Secondary - Indigo

| Variable | Tailwind | Usage |
|----------|----------|-------|
| `--secondary` | indigo-500 | Links, tabs, secondary actions |
| `--secondary-hover` | indigo-600 | Hover states |

```tsx
<a className="text-secondary hover:text-secondary-hover">Link</a>
```

### Accent - Sky/Cyan (Esports Flair)

| Variable | Tailwind | Usage |
|----------|----------|-------|
| `--accent` | sky-400 | Success glow, emphasis |
| `--interactive` | cyan-400 | Interactive elements, hover effects |

```tsx
<span className="text-accent">Featured</span>
<button className="hover:bg-interactive">Hover me</button>
```

---

## Background Scale (Slate)

| Class | Value | Usage |
|-------|-------|-------|
| `bg-base-950` | slate-950 | Deepest background |
| `bg-base-900` | slate-900+ | Page backgrounds |
| `bg-base-800` | slate-800 | Section backgrounds |
| `bg-base-700` | | Recessed panels |
| `bg-base-600` | | Deep cards |
| `bg-base-500` | slate-900 | Cards, elevated surfaces |
| `bg-base-400` | | Hover backgrounds |
| `bg-base-300` | slate-800 | Containers, modals |
| `bg-base-200` | | Cards, dropdowns |
| `bg-base-100` | slate-700 | Navbar, elevated elements |
| `bg-base-50` | | Brightest elevated surface |

**Dark Mode Logic**: Lower numbers = brighter (elevated), higher numbers = darker (recessed)

---

## Text Colors

| Class | Value | Usage |
|-------|-------|-------|
| `text-foreground` | slate-100 | Primary text |
| `text-text-secondary` | slate-300 | Secondary text, subtitles |
| `text-muted-foreground` | slate-400 | Muted/tertiary text |
| `text-link` | indigo-500 | Links |

---

## Status Colors (Intentional Accents)

Use accents **intentionally** - don't scatter random colors.

| Status | Color | Class | Usage |
|--------|-------|-------|-------|
| Success | emerald-400 | `text-success`, `bg-success` | Match won, completed |
| Warning | amber-400 | `text-warning`, `bg-warning` | Achievements, rankings |
| Error (text/badges) | rose-500 | `text-error`, `bg-destructive` | Inline errors, delete buttons |
| Error (surfaces) | red-900/violet-900 | `brandErrorBg` | Error containers — muted wine gradient |
| Error (cards) | red-900/60 | `brandErrorCard` | Error cards within containers |
| Info | sky-400 | `text-info`, `bg-info` | Informational callouts |
| Selection | violet-500 | `bg-selection` | Selected items |

```tsx
// Status examples
<span className="text-success">Match Won</span>
<span className="text-warning">1st Place</span>
<span className="text-error">Connection Lost</span>
<Badge className="bg-info">New Feature</Badge>
```

> **Error surfaces** use raw Tailwind colors (`red-900`, `violet-900`) instead of semantic `--error` tokens. This is intentional: error containers need deep wine/muted tones to maintain the "muted surfaces + bright accents" pattern. The semantic `rose-500` error token is for bright inline accents.

---

## Gradient Utilities

### Button Gradients

```tsx
// Standard button gradient (violet to indigo)
<button className="gradient-button">Action</button>

// Glow button gradient (purple-violet-indigo)
<button className="gradient-button-glow">Premium Action</button>
```

### Background Gradients

```tsx
// Subtle page gradient (slate-950 to slate-900)
<div className="gradient-bg-subtle min-h-screen">

// Hero banner with violet glow
<section className="gradient-hero">
```

### Glow Effects

```tsx
// Radial glow backgrounds
<div className="gradient-glow-violet">  {/* Violet glow */}
<div className="gradient-glow-cyan">    {/* Cyan glow */}

// Card hover glow
<div className="glow-hover">Card with hover glow</div>

// Neon border
<div className="border border-glow">Glowing border</div>
```

### Text Glow

```tsx
<h1 className="text-glow">Glowing Text</h1>
<h1 className="text-glow-violet">Violet Glow</h1>
<h1 className="text-glow-cyan">Cyan Glow</h1>
```

---

## Brand Button System

### Style Constants

All brand style constants are exported from `~/components/ui/buttons`:

| Constant | Tailwind Classes | Usage |
|----------|-----------------|-------|
| `brandGradient` | `bg-gradient-to-r from-violet-500 to-blue-500 hover:from-violet-400 hover:to-blue-400 text-white` | Primary CTA color |
| `brandSecondary` | `bg-gradient-to-r from-violet-500/30 to-blue-500/20 ring-1 ring-violet-300/60 text-violet-100 hover:from-violet-500/40 hover:to-blue-500/30` | Supporting actions |
| `brandErrorBg` | `bg-gradient-to-r from-red-900/40 to-violet-900/40 border border-red-500/20` | Error container surfaces |
| `brandErrorCard` | `bg-red-900/60 border border-red-500/15` | Error cards |
| `brandSuccessBg` | `[background-image:var(--brand-success-bg)]` | Success dialog surfaces (confirm dialogs) |
| `brandSecondaryOpaque` | `bg-violet-950 border border-violet-400/30 text-violet-100 hover:bg-violet-900` | Secondary on colored backgrounds (dialogs) |
| `brandBg` | `[background-image:var(--brand-bg)]` | Subtle surface background (default on dialogs) |
| `brandGlow` | `shadow-brand-glow` | Brand glow shadow |

### Brand Surface Background (`brandBg`)

All `Dialog` and `AlertDialog` content areas automatically include the `brandBg` gradient overlay. This provides a subtle violet-to-accent gradient on top of the solid `bg-background` base color.

**Why CSS variables?** `brandBg` uses `[background-image:var(--brand-bg)]` instead of Tailwind's `bg-gradient-to-*` utilities. This is critical because `tailwind-merge` treats `bg-gradient-to-*` and `bg-{color}` as the same CSS group — so a gradient would silently strip `bg-background` from the dialog, making it translucent. Using the arbitrary property `[background-image:...]` sets only `background-image` (the gradient overlay) without touching `background-color`, so both coexist.

The same pattern is used by `brandSuccessBg` for success dialog surfaces.

```tsx
// brandBg is automatic on Dialog/AlertDialog — no extra class needed
<DialogContent>...</DialogContent>

// For custom surfaces, import and apply manually
import { brandBg } from '~/components/ui/buttons/styles';
<div className={cn("bg-background", brandBg)}>Branded surface</div>
```

### 3D Depth Effects

Buttons support a `depth` prop for 3D press effects:

```tsx
// 3D button (default for PrimaryButton)
<PrimaryButton>Create</PrimaryButton>

// Flat button
<PrimaryButton depth={false}>Create</PrimaryButton>
```

The 3D system uses `button3DBase` (shadow, border-b-4, active press) and `button3DDisabled` (muted disabled state).

### Button Policy

**All new buttons should use `PrimaryButton` or `SecondaryButton`** unless there is a specific reason not to (e.g., icon-only buttons, dropdown triggers, shadcn component internals).

- **PrimaryButton**: Guides the user toward the most important action on screen — the button they're most likely to click. There should typically be one primary action per view/section.
- **SecondaryButton**: Everything else — supporting actions, cancel/back, contextual options.

Do **not** use `<Button>` directly for user-facing actions. Reserve `<Button>` for structural/internal uses only (dropdown triggers, combobox triggers, shadcn wrappers).

### Button Selection Guide

| Context | Component | Visual |
|---------|-----------|--------|
| Main CTA / most-clicked action | `<PrimaryButton>` | Brand gradient + 3D |
| Form submission | `<SubmitButton>` | Brand gradient + 3D |
| Dialog confirmation | `<ConfirmButton variant="success">` | Brand gradient + 3D |
| Destructive dialog action | `<ConfirmButton variant="destructive">` | Red + 3D |
| Warning dialog action | `<ConfirmButton variant="warning">` | Orange + 3D |
| Supporting/contextual action | `<SecondaryButton>` | Violet gradient + ring |
| Cancel/back/dismiss | `<SecondaryButton>` or `<CancelButton>` | Translucent violet |
| Colored contextual action | `<SecondaryButton color="sky">` | Colored background + 3D |
| Navigation action | `<NavButton>` | Sky blue + 3D |
| Edit action | `<EditButton>` | Purple + 3D |
| Destructive page action | `<DestructiveButton>` | Red + 3D |

> `PrimaryButton`, `SubmitButton`, and `ConfirmButton variant="success"` share the brand gradient visual. Choose based on HTML semantics and context, not appearance.

---

## Border Colors

| Class | Usage |
|-------|-------|
| `border-border` | Standard borders (slate-700) |
| `border-glow` | Glowing violet borders |
| `ring-ring` | Focus rings (violet-600) |

---

## Component Patterns

### Cards with Depth

```tsx
<div className="bg-base-300 border border-border rounded-lg p-4">
  <h3 className="text-foreground">Card Title</h3>
  <p className="text-muted-foreground">Description</p>
</div>

// With hover glow
<div className="bg-base-300 border border-border rounded-lg p-4 glow-hover">
```

### Buttons

```tsx
// Primary CTA (brand gradient + 3D depth)
<PrimaryButton>Create Tournament</PrimaryButton>
<PrimaryButton size="lg">Large CTA</PrimaryButton>

// Form submission
<SubmitButton loading={isSubmitting}>Save Changes</SubmitButton>

// Dialog confirmation
<ConfirmButton variant="success">Approve</ConfirmButton>
<ConfirmButton variant="destructive">Delete</ConfirmButton>

// Secondary (default brand violet gradient + ring)
<SecondaryButton>Settings</SecondaryButton>

// Secondary with colored background + 3D
<SecondaryButton color="cyan" depth>Colored Action</SecondaryButton>

// Avoid using <Button> directly for user-facing actions.
// Reserve for structural uses: dropdown triggers, combobox triggers, etc.
```

### Links & Tabs

```tsx
// Standard link
<a className="text-secondary hover:text-secondary-hover">Link</a>

// Using utility class
<a className="text-link">Auto-hover Link</a>
```

### Status Indicators

```tsx
// Win/Loss
<span className="text-success font-bold">WIN</span>
<span className="text-error font-bold">LOSS</span>

// Ranking badge
<span className="bg-warning text-warning-foreground px-2 py-1 rounded">
  1st
</span>

// Info callout
<div className="bg-info/10 border border-info text-info p-3 rounded">
  Draft starts in 5 minutes
</div>
```

---

## Navbar Styling

The navbar uses `bg-base-100` for elevation:

```tsx
<nav className="bg-base-100 shadow-sm">
  {/* Subtitle text uses text-text-secondary for visibility */}
  <span className="text-text-secondary">Subtitle</span>
</nav>
```

---

## Quick Reference

### Most Used Classes

```tsx
// Backgrounds
bg-base-900           // Page background
bg-base-300           // Cards, containers
bg-base-100           // Navbar, elevated
bg-primary            // Primary buttons
bg-secondary          // Secondary elements

// Text
text-foreground       // Primary text
text-muted-foreground // Muted text
text-text-secondary   // Subtitles, secondary
text-primary          // Brand color text
text-interactive      // Cyan accent text

// Status
text-success          // Green
text-warning          // Amber/gold
text-error            // Red
text-info             // Sky blue

// Effects
gradient-button       // Button gradient
glow-hover            // Hover glow effect
text-glow-violet      // Glowing text
border-glow           // Neon border

// Brand tokens (import from ~/components/ui/buttons)
brandGradient          // Primary CTA gradient (violet-to-blue)
brandSecondary         // Violet gradient + ring for secondary actions
brandErrorBg           // Muted wine error container
brandErrorCard         // Dark red error card
brandSuccessBg         // Success dialog surface gradient
brandSecondaryOpaque   // Opaque violet for colored backgrounds
brandBg                // Subtle brand surface gradient
brandGlow              // Brand glow shadow
```

### Color Values (oklch)

| Name | oklch | Approx Hex |
|------|-------|------------|
| violet-600 (primary) | `oklch(0.541 0.251 293)` | #7c3aed |
| indigo-500 (secondary) | `oklch(0.585 0.233 277)` | #6366f1 |
| cyan-400 (interactive) | `oklch(0.789 0.154 212)` | #22d3ee |
| sky-400 (accent) | `oklch(0.746 0.16 233)` | #38bdf8 |
| slate-950 (bg) | `oklch(0.129 0.042 265)` | #020617 |
| emerald-400 (success) | `oklch(0.765 0.177 163)` | #34d399 |
| amber-400 (warning) | `oklch(0.82 0.164 84)` | #fbbf24 |
| rose-500 (error) | `oklch(0.645 0.246 16)` | #f43f5e |

---

## Migration Notes

### From DaisyUI

Button classes map directly:
- `btn btn-primary` works as-is
- `btn btn-ghost`, `btn btn-outline` work as-is
- `bg-base-*` classes work with new values

### shadcn/ui Components

All shadcn components automatically use the theme:
- `<Button>` uses `--primary`
- `<Card>` uses `--card`
- Focus rings use `--ring` (violet)
