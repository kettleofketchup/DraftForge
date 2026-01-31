export const dialogWindowSize = '';
export interface ModalProps {
  children: React.ReactNode;
}

export const DIALOG_CSS =
  'min-w-full xl:min-w-[98%] sm:h-[95vh] sm:max-h-[95vh]';

export const SCROLLAREA_CSS =
  'overflow-y-auto overflow-x-auto h-screen max-h-[75vh] py-5em pr-2';

// Full screen modal for draft
export const DIALOG_CSS_FULLSCREEN =
  '!fixed !inset-0 !translate-x-0 !translate-y-0 !top-0 !left-0 !max-w-none !w-full !h-full !p-0 !gap-0 !rounded-none !border-0 overflow-hidden';

export const DIALOG_CSS_SMALL =
  'min-w-[98vw] h-[100vh] max-h-[98vh] sm:min-w-[26.563em] sm:h-[85vh] sm:h-max-[85vh] ';

export const SCROLLAREA_CSS_SMALL =
  'overflow-y-auto overflow-x-auto max-h-[65vh] py-5em pr-2 sm:h-[60vh] sm:h-max-[60vh] ';
