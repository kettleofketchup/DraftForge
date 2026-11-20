export const dialogWindowSize = '';
export interface ModalProps {
  children: React.ReactNode;
}

export const DIALOG_CSS =
  'min-w-full xl:min-w-[98%] sm:h-[95vh] sm:max-h-[95vh]';

/** Full-screen on phones, a centred dialog from `sm` (pair with a size). */
export const DIALOG_MOBILE_FULL_CSS =
  'h-full max-w-full rounded-none top-0 left-0 translate-x-0 translate-y-0 sm:max-w-[calc(100%-2rem)] sm:rounded-lg sm:top-[50%] sm:left-[50%] sm:translate-x-[-50%] sm:translate-y-[-50%]';

/**
 * FormDialog size="screen" (settings dialogs): full-screen on phones, 95vh
 * and full width on desktop, a flex column whose ScrollArea takes the rest.
 */
export const DIALOG_SCREEN_CSS = `${DIALOG_MOBILE_FULL_CSS} flex flex-col overflow-hidden ${DIALOG_CSS} data-[state=open]:!zoom-in-100 data-[state=closed]:!zoom-out-100`;

/** The ScrollArea under a DIALOG_SCREEN_CSS header: fills the rest, edge to edge. */
export const DIALOG_SCREEN_SCROLL_CSS =
  'flex-1 min-h-0 overflow-hidden -mx-6 px-6';

export const SCROLLAREA_CSS =
  'overflow-y-auto overflow-x-auto h-screen max-h-[75vh] py-5em pr-2';

// Full screen modal for draft
export const DIALOG_CSS_FULLSCREEN =
  '!fixed !inset-0 !translate-x-0 !translate-y-0 !top-0 !left-0 !max-w-none !w-full !h-full !p-0 !gap-0 !rounded-none !border-0 overflow-hidden';

export const DIALOG_CSS_SMALL =
  'min-w-[98vw] h-[100vh] max-h-[98vh] sm:min-w-[26.563em] sm:h-[85vh] sm:h-max-[85vh] ';

export const SCROLLAREA_CSS_SMALL =
  'overflow-y-auto overflow-x-auto max-h-[65vh] py-5em pr-2 sm:h-[60vh] sm:h-max-[60vh] ';
