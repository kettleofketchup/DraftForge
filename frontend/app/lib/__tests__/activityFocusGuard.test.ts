// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { installActivityFocusGuard } from '../activityFocusGuard';

describe('installActivityFocusGuard', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = '';
  });

  function input(): HTMLInputElement {
    const el = document.createElement('input');
    document.body.append(el);
    return el;
  }

  it('ignores programmatic focus while the activity does not have focus', () => {
    installActivityFocusGuard();
    vi.spyOn(document, 'hasFocus').mockReturnValue(false);
    const el = input();

    el.focus();

    expect(document.activeElement).toBe(document.body);
  });

  it('focuses normally while the activity has focus', () => {
    installActivityFocusGuard();
    vi.spyOn(document, 'hasFocus').mockReturnValue(true);
    const el = input();

    el.focus();

    expect(document.activeElement).toBe(el);
  });

  it('installs once', () => {
    installActivityFocusGuard();
    const guarded = HTMLElement.prototype.focus;
    installActivityFocusGuard();
    expect(HTMLElement.prototype.focus).toBe(guarded);
  });
});
