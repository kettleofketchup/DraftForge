/**
 * Shared button style constants for 3D effects and variants
 */

// Brand gradient - single source of truth for primary action buttons
export const brandGradient = 'bg-gradient-to-r from-violet-500 to-blue-500 hover:from-violet-400 hover:to-blue-400 text-white';

// Stroke + halo + cyan glow for labels sitting on brand-gradient surfaces.
export const brandLabelOnGradient =
  '[text-shadow:_0_1px_0_rgba(0,0,0,0.85),_0_2px_3px_rgba(0,0,0,0.5),_0_0_10px_var(--glow-cyan)] [&_svg]:text-white [&_svg]:drop-shadow-[0_1px_0_rgba(0,0,0,0.65)]';

// Brand secondary - supporting/contextual actions (subtle gradient + visible ring)
export const brandSecondary = 'bg-gradient-to-r from-violet-500/30 to-blue-500/20 ring-1 ring-violet-300/60 text-violet-100 hover:from-violet-500/40 hover:to-blue-500/30';

// Brand surface background - subtle purple gradient overlay matching homepage.
// Defined as --brand-bg in :root (app.css). Uses arbitrary property [background-image:...]
// instead of bg-gradient-to-* so tailwind-merge doesn't strip coexisting bg-{color} classes
// (e.g. bg-background on dialogs). Applied by default to Dialog and AlertDialog content.
export const brandBg = '[background-image:var(--brand-bg)]';

// Brand 3D depth colors — deep indigo bottom edge bridges the violet→blue
// gradient (instead of fighting it the way `violet-700` did), and the drop
// shadow swaps generic black for a brand-violet glow with a subtle 1px
// inner-top highlight that reads as "lit from above". Together this gives
// the brand primary a neon-cyber lift without the chunky-bevel feel.
export const brandDepthColors =
  'border-b-indigo-950 shadow-[0_8px_20px_-8px_var(--glow-violet),inset_0_1px_0_rgba(255,255,255,0.18)]';

// Brand glow shadow - visible on dark backgrounds, matches brand gradient
// Defined as --shadow-brand-glow in @theme (app.css) for use with variants
export const brandGlow = 'shadow-brand-glow';

// Brand success surface - emerald-to-violet gradient for confirm dialogs and success containers.
// Defined as --brand-success-bg in @theme (app.css). Uses arbitrary property to avoid
// tailwind-merge conflicts with bg-* (background-color).
export const brandSuccessBg = '[background-image:var(--brand-success-bg)]';

// Brand panel surface for content blocks placed *inside* a colored dialog
// (UserStrip, recap rows, etc.). Produces a darker, opaque-enough backdrop
// with a subtle hairline so the inner block reads as its own panel against
// the parent dialog's gradient — works on both lighter (success/emerald)
// and darker (destructive/red) surfaces. Compose via the caller's className
// so the inner component (e.g. <UserStrip>) merges via cn() / tailwind-merge.
export const brandDialogPanel = 'bg-black/40 ring-1 ring-white/10';

// Brand body text on colored surfaces — tonal harmony per variant. Each
// constant is a near-white tinted toward its surface's hue family, with a
// medium weight for presence and a hair of letter-spacing for sub-pixel
// sharpness on top of gradients. Use inside ConfirmDialog/AlertDialog
// descriptions, success/warning callouts, and any body copy that sits on a
// branded surface where the muted-foreground default fades.
//
//  brandReadableSuccess     → over brandSuccessBg / emerald gradients
//  brandReadableWarning     → over warning / orange gradients
//  brandReadableDestructive → over destructive / red gradients
//
// The color uses Tailwind's `!` modifier because shadcn primitives like
// AlertDialogDescription apply their own `text-muted-foreground` via Radix
// Slot, which concatenates classNames (no tailwind-merge) — without `!` the
// two text-color rules collide in source order.
//
// Body copy only — never use these for headlines, and never pair with a
// text-shadow outline (use `text-outline-black` on display type instead).
export const brandReadableSuccess =
  '!text-emerald-50 font-medium tracking-[0.005em]';
export const brandReadableWarning =
  '!text-orange-50 font-medium tracking-[0.005em]';
export const brandReadableDestructive =
  '!text-rose-50 font-medium tracking-[0.005em]';

// Brand highlight - emerald-to-violet cyberpunk gradient for featured info (org links, stats, callouts).
export const brandHighlight = 'bg-gradient-to-r from-emerald-900/40 to-violet-900/40 border border-emerald-500/20 hover:from-emerald-900/60 hover:to-violet-900/60';
export const brandHighlightText = 'bg-gradient-to-r from-emerald-400 to-violet-400 bg-clip-text text-transparent';

// Brand toxic - violet → deep-emerald cyberpunk gradient for edit
// affordances. Same palette family as `brandHighlight` (emerald + violet)
// but darker and smoothly blended through a deep-violet/emerald midpoint.
// Reads as "toxic ooze" — saturated, dark, with no harsh hue line.
// Used by <EditButton> / <EditIconButton> so every edit affordance pops
// against the slate base without competing with the primary CTA gradient.
export const brandToxic =
  'bg-gradient-to-br from-violet-700 via-emerald-800 to-emerald-700 hover:from-violet-600 hover:via-emerald-700 hover:to-emerald-600 text-white';
export const brandToxicDepthColors = 'border-b-emerald-900 shadow-emerald-950/60';

// Brand error surfaces - muted deep wine/red tones for error containers.
// Uses raw Tailwind colors (not semantic --error/--primary) because error surfaces
// need deep wine/muted tones, not the bright accent status colors.
export const brandErrorBg = 'bg-gradient-to-r from-red-900/40 to-violet-900/40 border border-red-500/20';
export const brandErrorCard = 'bg-red-900/60 border border-red-500/15';
// Brand error primary - lighter red for interactive error elements (buttons, close icons)
export const brandErrorPrimary = 'bg-gradient-to-r from-red-700/80 to-violet-900/80 hover:from-red-600/80 hover:to-violet-800/80 text-white';

// Base button lift — flat by design. The old chunky bevel
// (`border-b-4 active:border-b-0 active:translate-y-1`) was removed so action
// buttons read clean and consistent (no mix of 3D / non-3D across a footer).
// A soft drop shadow keeps the surface separated from the dialog; press
// feedback comes from <Button>'s `active:scale-[0.95]` (button.tsx). Per-variant
// `border-b-<color>` accents below are now inert (width 0) and harmless.
export const button3DBase =
  'shadow-lg shadow-black/30 transition-all duration-75';

// Disabled state styling - removes lift and uses muted colors
export const button3DDisabled =
  'disabled:shadow-none disabled:bg-gray-400 disabled:text-gray-600 disabled:cursor-not-allowed disabled:opacity-70';

// Icon styling to ensure icons inherit text color
const iconWhite = '[&_svg]:text-white [&_svg]:drop-shadow-[1px_1px_1px_rgba(0,0,0,0.5)]';
const iconMuted = 'disabled:[&_svg]:text-gray-600 disabled:[&_svg]:drop-shadow-none';

// Brand secondary opaque - for use on colored backgrounds (dialogs) where translucency bleeds
export const brandSecondaryOpaque = 'bg-violet-950 border border-violet-400/30 text-violet-100 hover:bg-violet-900';

// Brand secondary with 3D depth
export const brandSecondary3D = `${button3DBase} ${button3DDisabled} ${brandSecondary} border-b-violet-700/50`;

// Brand secondary opaque with 3D depth (for colored dialog backgrounds)
export const brandSecondaryOpaque3D = `${button3DBase} ${button3DDisabled} ${brandSecondaryOpaque} border-b-violet-700/50`;

// Neutral opaque - gray/slate for cancel buttons on colored dialog backgrounds
export const brandNeutralOpaque = 'bg-slate-700 border border-slate-500/30 text-slate-100 hover:bg-slate-600';
export const brandNeutralOpaque3D = `${button3DBase} ${button3DDisabled} ${brandNeutralOpaque} border-b-slate-800/50`;

// Variant-specific 3D styles with disabled state
export const button3DVariants = {
  destructive: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-red-600 text-white hover:bg-red-500 border-b-red-800 shadow-red-900/50`,
  warning: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-orange-500 text-white hover:bg-orange-400 border-b-orange-700 shadow-orange-900/50`,
  success: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} ${brandGradient} ${brandDepthColors}`,
  primary: `${button3DBase} ${button3DDisabled} bg-primary text-primary-foreground hover:bg-primary/90 border-b-primary/50`,
  secondary: `${brandSecondary3D}`,
  outline: `${button3DBase} ${button3DDisabled} border-b-gray-600`,
  edit: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} ${brandToxic} ${brandToxicDepthColors}`,
  nav: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-sky-700 text-white hover:bg-sky-600 border-b-sky-900 shadow-sky-900/50`,
} as const;

export type Button3DVariant = keyof typeof button3DVariants;
