/**
 * Shared button style constants for 3D effects and variants
 */

// Brand gradient - single source of truth for primary action buttons
export const brandGradient = 'bg-gradient-to-r from-violet-500 to-blue-500 hover:from-violet-400 hover:to-blue-400 text-white';

// Brand secondary - supporting/contextual actions (subtle gradient + visible ring)
export const brandSecondary = 'bg-gradient-to-r from-violet-500/30 to-blue-500/20 ring-1 ring-violet-300/60 text-violet-100 hover:from-violet-500/40 hover:to-blue-500/30';

// Brand surface background - subtle purple gradient overlay matching homepage.
// Defined as --brand-bg in :root (app.css). Uses arbitrary property [background-image:...]
// instead of bg-gradient-to-* so tailwind-merge doesn't strip coexisting bg-{color} classes
// (e.g. bg-background on dialogs). Applied by default to Dialog and AlertDialog content.
export const brandBg = '[background-image:var(--brand-bg)]';

// Brand 3D depth colors - violet border-bottom with neutral shadow
export const brandDepthColors = 'border-b-violet-700 shadow-black/30';

// Brand glow shadow - visible on dark backgrounds, matches brand gradient
// Defined as --shadow-brand-glow in @theme (app.css) for use with variants
export const brandGlow = 'shadow-brand-glow';

// Brand success surface - emerald-to-violet gradient for confirm dialogs and success containers.
// Defined as --brand-success-bg in @theme (app.css). Uses arbitrary property to avoid
// tailwind-merge conflicts with bg-* (background-color).
export const brandSuccessBg = '[background-image:var(--brand-success-bg)]';

// Brand error surfaces - muted deep wine/red tones for error containers.
// Uses raw Tailwind colors (not semantic --error/--primary) because error surfaces
// need deep wine/muted tones, not the bright accent status colors.
export const brandErrorBg = 'bg-gradient-to-r from-red-900/40 to-violet-900/40 border border-red-500/20';
export const brandErrorCard = 'bg-red-900/60 border border-red-500/15';
// Brand error primary - lighter red for interactive error elements (buttons, close icons)
export const brandErrorPrimary = 'bg-gradient-to-r from-red-700/80 to-violet-900/80 hover:from-red-600/80 hover:to-violet-800/80 text-white';

// Base 3D button effect classes (active state removed for disabled buttons via CSS)
export const button3DBase =
  'shadow-lg shadow-black/30 border-b-4 active:border-b-0 active:translate-y-1 transition-all duration-75';

// Disabled state styling - removes 3D effects and uses muted colors
export const button3DDisabled =
  'disabled:shadow-none disabled:border-b-0 disabled:translate-y-0 disabled:bg-gray-400 disabled:text-gray-600 disabled:cursor-not-allowed disabled:opacity-70';

// Icon styling to ensure icons inherit text color
const iconWhite = '[&_svg]:text-white [&_svg]:drop-shadow-[1px_1px_1px_rgba(0,0,0,0.5)]';
const iconMuted = 'disabled:[&_svg]:text-gray-600 disabled:[&_svg]:drop-shadow-none';

// Brand secondary opaque - for use on colored backgrounds (dialogs) where translucency bleeds
export const brandSecondaryOpaque = 'bg-violet-950 border border-violet-400/30 text-violet-100 hover:bg-violet-900';

// Brand secondary with 3D depth
export const brandSecondary3D = `${button3DBase} ${button3DDisabled} ${brandSecondary} border-b-violet-700/50`;

// Brand secondary opaque with 3D depth (for colored dialog backgrounds)
export const brandSecondaryOpaque3D = `${button3DBase} ${button3DDisabled} ${brandSecondaryOpaque} border-b-violet-700/50`;

// Variant-specific 3D styles with disabled state
export const button3DVariants = {
  destructive: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-red-600 text-white hover:bg-red-500 border-b-red-800 shadow-red-900/50`,
  warning: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-orange-500 text-white hover:bg-orange-400 border-b-orange-700 shadow-orange-900/50`,
  success: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} ${brandGradient} ${brandDepthColors}`,
  primary: `${button3DBase} ${button3DDisabled} bg-primary text-primary-foreground hover:bg-primary/90 border-b-primary/50`,
  secondary: `${brandSecondary3D}`,
  outline: `${button3DBase} ${button3DDisabled} border-b-gray-600`,
  edit: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-purple-700 text-white hover:bg-purple-600 border-b-purple-900 shadow-purple-900/50`,
  nav: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-sky-700 text-white hover:bg-sky-600 border-b-sky-900 shadow-sky-900/50`,
} as const;

export type Button3DVariant = keyof typeof button3DVariants;
