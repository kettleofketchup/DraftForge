/**
 * Shared button style constants for 3D effects and variants
 */

// Text shadow for 3D pop effect on button text
export const buttonTextShadow = '[text-shadow:_1px_1px_2px_rgb(0_0_0_/_60%),_0_1px_3px_rgb(0_0_0_/_40%)]';

// Base 3D button effect classes (active state removed for disabled buttons via CSS)
export const button3DBase =
  `shadow-lg shadow-black/30 border-b-4 active:border-b-0 active:translate-y-1 transition-all duration-75 ${buttonTextShadow}`;

// Disabled state styling - removes 3D effects and uses muted colors
export const button3DDisabled =
  'disabled:shadow-none disabled:border-b-0 disabled:translate-y-0 disabled:bg-gray-400 disabled:text-gray-600 disabled:cursor-not-allowed disabled:opacity-70 disabled:[text-shadow:none]';

// Icon styling to ensure icons inherit text color
const iconWhite = '[&_svg]:text-white [&_svg]:fill-white [&_svg]:drop-shadow-[1px_1px_1px_rgba(0,0,0,0.5)]';
const iconMuted = 'disabled:[&_svg]:text-gray-600 disabled:[&_svg]:fill-gray-600 disabled:[&_svg]:drop-shadow-none';

// Variant-specific 3D styles with disabled state
export const button3DVariants = {
  destructive: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-red-600 text-white hover:bg-red-500 border-b-red-800 shadow-red-900/50`,
  warning: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-orange-500 text-white hover:bg-orange-400 border-b-orange-700 shadow-orange-900/50`,
  success: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-green-600 text-white hover:bg-green-500 border-b-green-800 shadow-green-900/50`,
  primary: `${button3DBase} ${button3DDisabled} bg-primary text-primary-foreground hover:bg-primary/90 border-b-primary/50`,
  secondary: `${button3DBase} ${button3DDisabled} bg-secondary text-secondary-foreground hover:bg-secondary/80 border-b-secondary/50`,
  outline: `${button3DBase} ${button3DDisabled} border-b-gray-600`,
  edit: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-purple-700 text-white hover:bg-purple-600 border-b-purple-900 shadow-purple-900/50`,
  nav: `${button3DBase} ${button3DDisabled} ${iconWhite} ${iconMuted} bg-sky-700 text-white hover:bg-sky-600 border-b-sky-900 shadow-sky-900/50`,
} as const;

export type Button3DVariant = keyof typeof button3DVariants;
