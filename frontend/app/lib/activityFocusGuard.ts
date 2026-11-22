const GUARDED = Symbol.for('draftforge.activityFocusGuard');

type Focusable = typeof HTMLElement | typeof SVGElement;

/**
 * Inside the Discord iframe, element.focus() pulls keyboard focus out of
 * Discord even when the user is typing there. Radix focus traps do this on
 * every DOM change, so focus calls are dropped until the activity has focus.
 */
export function installActivityFocusGuard(): void {
  for (const ctor of [HTMLElement, SVGElement] as Focusable[]) {
    const proto = ctor.prototype as HTMLElement & { [GUARDED]?: true };
    if (proto[GUARDED]) continue;
    const focus = proto.focus;
    proto.focus = function (this: HTMLElement, options?: FocusOptions) {
      if (!this.ownerDocument.hasFocus()) return;
      focus.call(this, options);
    };
    proto[GUARDED] = true;
  }
}
