# DraftForge Theming Guide

## Theme Overview

**Visual Vibe**: Neon Cyber Esports | Dota-style Draft UI | Dark Mode First

This theme uses a violet/indigo primary palette with cyan accents for an esports-focused, competitive gaming aesthetic.

**Location**: `frontend/app/app.css`

---

## Color Palette

### Primary (Brand) - Violet

| Variable | Tailwind | Usage |
|----------|----------|-------|
| `--primary` | violet-600 | Main buttons, highlights |
| `--primary-hover` | violet-500 | Hover states |
| `--primary-active` | violet-700 | Active/pressed states |

```tsx
<Button>Primary Action</Button>
<button className="bg-primary hover:bg-primary-hover">Click</button>
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
| Error | rose-500 | `text-error`, `bg-destructive` | Errors, delete actions |
| Info | sky-400 | `text-info`, `bg-info` | Informational callouts |
| Selection | violet-500 | `bg-selection` | Selected items |

```tsx
// Status examples
<span className="text-success">Match Won</span>
<span className="text-warning">1st Place</span>
<span className="text-error">Connection Lost</span>
<Badge className="bg-info">New Feature</Badge>
```

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
// Primary (violet)
<Button>Primary</Button>
<button className="btn btn-primary">Primary</button>

// Secondary (indigo)
<Button variant="secondary">Secondary</Button>

// Ghost
<Button variant="ghost">Ghost</Button>

// Destructive (rose)
<Button variant="destructive">Delete</Button>

// With gradient
<button className="gradient-button rounded-lg px-4 py-2 text-white">
  Gradient Button
</button>
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
