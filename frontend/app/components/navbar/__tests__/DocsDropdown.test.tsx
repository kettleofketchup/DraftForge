// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HIDE_DELAY_MS } from '~/components/ui/shared-popover-context';
import { LocationProbe, probeNavigate } from '~/test-utils/LocationProbe';
import '../changelog/ChangelogPreview';
import { DocsDropdown, HOVER_OPEN_DELAY_MS } from '../DocsDropdown';
import { DOCS_URL } from '../links';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('~/data/CHANGELOG.md?raw', async () => ({
  default: (await import('~/lib/__tests__/changelog-fixture'))
    .CHANGELOG_FIXTURE,
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

window.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;

function renderDropdown() {
  render(
    <MemoryRouter>
      <DocsDropdown />
      <input data-testid="other" />
      <LocationProbe />
    </MemoryRouter>,
  );
  return screen.getByTestId('nav-docs-trigger');
}

const panel = () => screen.queryByTestId('nav-docs-panel');
const advance = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
const hover = (el: Element) =>
  fireEvent.pointerEnter(el, { pointerType: 'mouse' });
const leave = (el: Element) =>
  fireEvent.pointerLeave(el, { pointerType: 'mouse' });

async function hoverOpen() {
  const trigger = renderDropdown();
  hover(trigger);
  await advance(HOVER_OPEN_DELAY_MS);
  expect(panel()).not.toBeNull();
  return trigger;
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('DocsDropdown with real timers', () => {
  it('opens on click with the docs link and the two latest releases', async () => {
    const trigger = renderDropdown();
    expect(trigger.tagName).toBe('BUTTON');
    expect(trigger.getAttribute('aria-label')).toBe('aria.documentation');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(trigger);

    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByTestId('nav-docs-panel')).toBeTruthy();
    expect(screen.getByRole('dialog', { name: 'nav.whats_new' })).toBeTruthy();
    expect(
      screen.getByRole('heading', { level: 2, name: 'nav.whats_new' }),
    ).toBeTruthy();
    expect(
      await screen.findByRole('heading', { level: 3, name: /2\.1\.0/ }),
    ).toBeTruthy();
    expect(
      screen.getByRole('heading', { level: 3, name: /2\.0\.0/ }),
    ).toBeTruthy();
    expect(
      screen.getByRole('heading', { level: 4, name: 'Fixed' }),
    ).toBeTruthy();
    const docs = screen.getByTestId('nav-docs-documentation-link');
    expect(docs.getAttribute('href')).toBe(DOCS_URL);
    expect(docs.getAttribute('target')).toBe('_blank');
    expect(docs.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('opens with Enter/Space (detail 0 click) and Escape returns focus to the trigger', async () => {
    const trigger = renderDropdown();
    for (let i = 0; i < 2; i++) {
      act(() => trigger.focus());
      fireEvent.click(trigger, { detail: 0 });
      expect(await screen.findByTestId('nav-docs-panel')).toBeTruthy();
      fireEvent.keyDown(document.activeElement ?? document.body, {
        key: 'Escape',
      });
      expect(panel()).toBeNull();
      await waitFor(() => expect(document.activeElement).toBe(trigger));
    }
  });

  it('closes when the Full changelog link is clicked', async () => {
    const trigger = renderDropdown();
    fireEvent.click(trigger);
    fireEvent.click(await screen.findByTestId('nav-changelog-full-link'));
    expect(panel()).toBeNull();
    expect(screen.getByTestId('location').textContent).toBe('/changelog');
  });

  it('renders the changelog preview wrapper inside the panel', async () => {
    fireEvent.click(renderDropdown());
    const preview = await screen.findByTestId('nav-changelog-preview');
    expect(screen.getByTestId('nav-docs-panel').contains(preview)).toBe(true);
  });

  it('closes when the route changes', async () => {
    fireEvent.click(renderDropdown());
    expect(await screen.findByTestId('nav-docs-panel')).toBeTruthy();
    act(() => probeNavigate.current!('/x'));
    expect(screen.getByTestId('location').textContent).toBe('/x');
    expect(panel()).toBeNull();
  });
});

describe('DocsDropdown hover behaviour', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  });

  it('opens only after the hover delay, and not if the pointer leaves first', async () => {
    const trigger = renderDropdown();
    hover(trigger);
    await advance(HOVER_OPEN_DELAY_MS - 1);
    expect(panel()).toBeNull();
    await advance(1);
    expect(panel()).not.toBeNull();

    cleanup();
    const again = renderDropdown();
    hover(again);
    await advance(HOVER_OPEN_DELAY_MS - 1);
    leave(again);
    await advance(HOVER_OPEN_DELAY_MS * 2);
    expect(panel()).toBeNull();
  });

  it('closes after the grace period when the pointer leaves', async () => {
    const trigger = await hoverOpen();
    leave(trigger);
    await advance(HIDE_DELAY_MS - 1);
    expect(panel()).not.toBeNull();
    await advance(1);
    expect(panel()).toBeNull();
  });

  it('stays open when the pointer moves from the trigger into the panel', async () => {
    const trigger = await hoverOpen();
    leave(trigger);
    await advance(HIDE_DELAY_MS - 50);
    hover(panel()!);
    await advance(HIDE_DELAY_MS * 2);
    expect(panel()).not.toBeNull();
  });

  it('stays open after pointer leave while focus is inside the panel', async () => {
    const trigger = await hoverOpen();
    act(() => screen.getByTestId('nav-docs-documentation-link').focus());
    leave(trigger);
    await advance(HIDE_DELAY_MS * 2);
    expect(panel()).not.toBeNull();
  });

  it('a click after a hover-open pins the panel, a second click closes it', async () => {
    const trigger = await hoverOpen();
    fireEvent.click(trigger);
    expect(panel()).not.toBeNull();
    leave(trigger);
    await advance(HIDE_DELAY_MS * 2);
    expect(panel()).not.toBeNull();
    fireEvent.click(trigger);
    expect(panel()).toBeNull();
  });

  it('a touch pointerenter does not open it', async () => {
    const trigger = renderDropdown();
    fireEvent.pointerEnter(trigger, { pointerType: 'touch' });
    await advance(HOVER_OPEN_DELAY_MS * 2);
    expect(panel()).toBeNull();
  });

  it('hover open and close never steal focus from another input', async () => {
    const trigger = renderDropdown();
    const other = screen.getByTestId('other');
    act(() => other.focus());
    hover(trigger);
    await advance(HOVER_OPEN_DELAY_MS);
    expect(panel()).not.toBeNull();
    expect(document.activeElement).toBe(other);
    leave(trigger);
    await advance(HIDE_DELAY_MS);
    expect(panel()).toBeNull();
    expect(document.activeElement).toBe(other);
  });

  it('a hover-opened panel closes when focus leaves it', async () => {
    const trigger = await hoverOpen();
    act(() => screen.getByTestId('nav-docs-documentation-link').focus());
    leave(trigger);
    await advance(HIDE_DELAY_MS * 2);
    expect(panel()).not.toBeNull();

    act(() => screen.getByTestId('other').focus());
    expect(panel()).toBeNull();
    await advance(HIDE_DELAY_MS * 2);
    expect(panel()).toBeNull();
  });
});
