// Shared styles
export { brandBg, brandDepthColors, brandDialogPanel, brandErrorBg, brandErrorCard, brandErrorPrimary, brandGlow, brandGradient, brandHighlight, brandHighlightText, brandReadableDestructive, brandReadableSuccess, brandReadableWarning, brandSecondary, brandSecondary3D, brandSecondaryOpaque, brandSecondaryOpaque3D, brandSuccessBg, button3DBase, button3DDisabled, button3DVariants } from './styles';
export type { Button3DVariant } from './styles';

// Shared affordances
export { HotkeyBadge } from './HotkeyBadge';
export type { HotkeyBadgeProps } from './HotkeyBadge';

// Base Buttons
export { AddDiscordBotButton } from './AddDiscordBotButton';
export type { AddDiscordBotButtonProps } from './AddDiscordBotButton';

export { CancelButton } from './CancelButton';
export type { CancelButtonProps, CancelButtonVariant } from './CancelButton';

export { ConfirmButton } from './ConfirmButton';

export { HighlightButton } from './HighlightButton';
export type { HighlightButtonProps } from './HighlightButton';
export type { ConfirmButtonProps, ConfirmButtonVariant } from './ConfirmButton';

export { DestructiveButton } from './DestructiveButton';
export type { DestructiveButtonProps } from './DestructiveButton';

export { EditButton } from './EditButton';
export type { EditButtonProps } from './EditButton';

export { HistoryButton } from './HistoryButton';
export type { HistoryButtonProps } from './HistoryButton';

export { NavButton } from './NavButton';
export type { NavButtonProps, NavDirection } from './NavButton';

export { PrimaryButton } from './PrimaryButton';
export type { PrimaryButtonColor, PrimaryButtonProps } from './PrimaryButton';

export { SecondaryButton } from './SecondaryButton';
export type { SecondaryColor, SecondaryButtonProps } from './SecondaryButton';

export { SubmitButton } from './SubmitButton';
export type { SubmitButtonProps } from './SubmitButton';

export { WarningButton } from './WarningButton';
export type { WarningButtonProps } from './WarningButton';

// Icon Buttons
export {
  ChevronNavButton,
  EditIconButton,
  PlusIconButton,
  SendIconButton,
  TrashIconButton,
  ViewIconButton,
  ZoomIconButton,
} from './icons';

export type {
  ChevronDirection,
  ChevronNavButtonProps,
  EditIconButtonProps,
  IconButtonSize,
  PlusIconButtonProps,
  SendIconButtonProps,
  TrashIconButtonProps,
  ViewIconButtonProps,
  ZoomAction,
  ZoomIconButtonProps,
} from './icons';

// User-domain buttons (Dotabuff, etc.) — see ./user/README context note.
export { DotabuffButton, DotabuffIconButton } from './user';
export type { DotabuffButtonProps, DotabuffIconButtonProps } from './user';
