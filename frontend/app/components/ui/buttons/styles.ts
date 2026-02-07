/**
 * Shared button style constants for 3D effects and variants
 */

// Brand gradient - single source of truth for primary action buttons
export const brandGradient = 'bg-gradient-to-r from-violet-500 to-blue-500 hover:from-violet-400 hover:to-blue-400 text-white';

// Brand secondary - supporting/contextual actions
export const brandSecondary = 'bg-violet-500/20 border border-violet-400/30 text-violet-100 hover:bg-violet-500/30';

// Brand surface background - subtle violet tint for section panels
export const brandBg = 'bg-violet-950/40';

// Brand 3D depth colors - violet border-bottom and shadow for brand gradient buttons
export const brandDepthColors = 'border-b-violet-700 shadow-violet-900/50';

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
const iconWhite = '[&_svg]:text-white [&_svg]:fill-white [&_svg]:drop-shadow-[1px_1px_1px_rgba(0,0,0,0.5)]';
const iconMuted = 'disabled:[&_svg]:text-gray-600 disabled:[&_svg]:fill-gray-600 disabled:[&_svg]:drop-shadow-none';

// Variant-specific 3D styles with disabled state
export const button3DVariants = {
  destructive: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-red-600 text-white hover:bg-red-500 border-b-red-800 shadow-red-900/50`,
  warning: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-orange-500 text-white hover:bg-orange-400 border-b-orange-700 shadow-orange-900/50`,
  success: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} ${brandGradient} ${brandDepthColors}`,
  primary: `${button3DBase} ${button3DDisabled} bg-primary text-primary-foreground hover:bg-primary/90 border-b-primary/50`,
  secondary: `${button3DBase} ${button3DDisabled} bg-secondary text-secondary-foreground hover:bg-secondary/80 border-b-secondary/50`,
  outline: `${button3DBase} ${button3DDisabled} border-b-gray-600`,
  edit: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-purple-700 text-white hover:bg-purple-600 border-b-purple-900 shadow-purple-900/50`,
  nav: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-sky-700 text-white hover:bg-sky-600 border-b-sky-900 shadow-sky-900/50`,
} as const;

export type Button3DVariant = keyof typeof button3DVariants;
