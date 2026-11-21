const OPEN_LAYER_SELECTOR =
  '[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]';

export function isOverlaidByOtherLayer(anchor: Element | null): boolean {
  const layers = document.querySelectorAll(OPEN_LAYER_SELECTOR);
  return Array.from(layers).some((layer) => !layer.contains(anchor));
}

export function isMenuOpen(): boolean {
  return document.querySelector('[role="menu"], [role="listbox"]') !== null;
}

const TEXT_ENTRY_SELECTOR =
  'input, textarea, select, [contenteditable=""], [contenteditable="true"], [role="textbox"], [role="combobox"], [role="menuitem"], [role="option"]';
const ACTIVATABLE_SELECTOR = 'button, a[href], summary, [role="button"]';

function isFocusVisible(el: Element): boolean {
  try {
    return el.matches(':focus-visible');
  } catch {
    return true;
  }
}

/** Whether Enter on `el` already means something: typing, or a keyboard-focused control. */
export function ownsEnterKey(el: Element | null): boolean {
  if (!(el instanceof Element)) return false;
  if (el.matches(TEXT_ENTRY_SELECTOR)) return true;
  return el.matches(ACTIVATABLE_SELECTOR) && isFocusVisible(el);
}
