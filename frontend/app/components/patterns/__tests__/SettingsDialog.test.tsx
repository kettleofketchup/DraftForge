// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { SettingsDialog, type SettingsSection } from '../SettingsDialog';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= vi.fn();

function Toggled() {
  const [on, setOn] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOn(true)}>
        enable password
      </button>
      {on && (
        <>
          <label htmlFor="password-input">Lobby password</label>
          <input id="password-input" />
        </>
      )}
    </div>
  );
}

const sections: SettingsSection[] = [
  {
    value: 'general',
    label: 'General',
    content: (
      <div>
        <label htmlFor="name-input">Event name</label>
        <input id="name-input" />
      </div>
    ),
  },
  {
    value: 'lobby',
    label: 'Lobby',
    content: (
      <div>
        <h3>Dota Lobbies</h3>
        <label htmlFor="region-input">Lobby region</label>
        <input id="region-input" />
        <Toggled />
      </div>
    ),
  },
  {
    value: 'discord',
    label: 'Discord',
    lazy: true,
    keywords: ['channel'],
    content: <label>Announcement channel</label>,
  },
];

const onSubmit = vi.fn();

function Harness({ items = sections }: { items?: SettingsSection[] }) {
  return (
    <TooltipProvider>
      <SettingsDialog
        open
        onOpenChange={() => {}}
        title="Settings"
        onSubmit={onSubmit}
        sections={items}
        testIdPrefix="s"
      />
    </TooltipProvider>
  );
}

const search = () => screen.getByTestId('s-search');
const type = (value: string) =>
  fireEvent.change(search(), { target: { value } });
const navItem = (value: string) => screen.queryByTestId(`s-tab-${value}`);
const hitLabels = () =>
  screen
    .queryAllByTestId('s-search-hit')
    .map((h) => h.querySelector('span')?.textContent);
const frame = () => new Promise((r) => requestAnimationFrame(r));

function mockViewport(initialMobile: boolean) {
  let mobile = initialMobile;
  const listeners = new Set<() => void>();
  window.matchMedia = ((query: string) => ({
    get matches() {
      return query.includes('max-width') ? mobile : false;
    },
    media: query,
    addEventListener: (_: string, cb: () => void) => listeners.add(cb),
    removeEventListener: (_: string, cb: () => void) => listeners.delete(cb),
  })) as unknown as typeof window.matchMedia;
  return (next: boolean) => {
    mobile = next;
    act(() => listeners.forEach((cb) => cb()));
  };
}

describe('SettingsDialog', () => {
  const originalMatchMedia = window.matchMedia;
  beforeEach(() => onSubmit.mockClear());
  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it('renders the categories as vertical tabs in a sidebar', () => {
    render(<Harness />);
    expect(screen.getByTestId('s-sidebar')).toBeInTheDocument();
    expect(screen.getByRole('tablist')).toHaveAttribute(
      'aria-orientation',
      'vertical',
    );
    expect(navItem('general')).toHaveAttribute('data-state', 'active');
    expect(navItem('lobby')).toHaveAttribute('role', 'tab');
  });

  it('filters categories by name and keywords, keeping the active one', () => {
    render(<Harness />);
    type('channel');
    expect(navItem('discord')).toBeInTheDocument();
    expect(navItem('lobby')).toBeNull();
    // Active category stays reachable even when it doesn't match.
    expect(navItem('general')).toBeInTheDocument();
  });

  it('lists matching labels and headings outside the tablist', () => {
    render(<Harness />);
    type('lobb');
    expect(hitLabels()).toEqual(['Dota Lobbies', 'Lobby region']);
    expect(screen.getAllByTestId('s-search-hit')[0]).toHaveTextContent('Lobby');
    const tablist = screen.getByRole('tablist');
    for (const hit of screen.getAllByTestId('s-search-hit')) {
      expect(tablist.contains(hit)).toBe(false);
    }
  });

  it('announces the match count', () => {
    render(<Harness />);
    type('lobb');
    expect(screen.getByRole('status')).toHaveTextContent('2 matching settings');
    type('zzz');
    expect(screen.getByRole('status')).toHaveTextContent(
      'No settings match “zzz”',
    );
  });

  it('matches every search term, in any order', () => {
    render(<Harness />);
    type('region lobby');
    expect(hitLabels()).toEqual(['Lobby region']);
  });

  it('jumps to a field hit: selects its category and focuses its control', async () => {
    render(<Harness />);
    type('region');
    fireEvent.click(screen.getByTestId('s-search-hit'));
    expect(navItem('lobby')).toHaveAttribute('data-state', 'active');
    await frame();
    expect(document.activeElement).toBe(
      document.getElementById('region-input'),
    );
  });

  it('jumps to a heading hit and focuses the heading', async () => {
    render(<Harness />);
    type('dota lobbies');
    fireEvent.click(screen.getByTestId('s-search-hit'));
    await frame();
    const heading = screen.getByRole('heading', { name: 'Dota Lobbies' });
    expect(document.activeElement).toBe(heading);
    expect(heading).toHaveAttribute('data-search-hit');
  });

  it('re-indexes when fields appear while searching', async () => {
    render(<Harness />);
    type('password');
    expect(hitLabels()).toEqual([]);
    fireEvent.click(screen.getByText('enable password'));
    await vi.waitFor(() => expect(hitLabels()).toEqual(['Lobby password']));
  });

  it('Enter in search jumps to the first hit instead of submitting', () => {
    render(<Harness />);
    type('region');
    fireEvent.keyDown(search(), { key: 'Enter' });
    expect(onSubmit).not.toHaveBeenCalled();
    expect(navItem('lobby')).toHaveAttribute('data-state', 'active');
  });

  it('Escape clears a non-empty search', () => {
    render(<Harness />);
    type('region');
    fireEvent.keyDown(search(), { key: 'Escape' });
    expect(search()).toHaveValue('');
    expect(navItem('discord')).toBeInTheDocument();
  });

  it('says so when nothing matches', () => {
    render(<Harness />);
    type('zzz');
    expect(screen.getByTestId('s-search-empty')).toHaveTextContent('zzz');
  });

  it('searches a lazy category only by name and keywords until visited', () => {
    render(<Harness />);
    type('announcement');
    expect(screen.queryByTestId('s-search-hit')).toBeNull();
    type('');
    fireEvent.mouseDown(navItem('discord')!, { button: 0 });
    type('announcement');
    expect(hitLabels()).toEqual(['Announcement channel']);
  });

  it('marks categories holding invalid fields', () => {
    render(
      <Harness
        items={sections.map((s) =>
          s.value === 'lobby' ? { ...s, invalid: true } : s,
        )}
      />,
    );
    expect(navItem('lobby')).toHaveAttribute('data-invalid', 'true');
    expect(navItem('general')).not.toHaveAttribute('data-invalid');
  });

  it('"/" focuses the search box, but not from a text field', () => {
    render(<Harness />);
    const name = document.getElementById('name-input')!;
    name.focus();
    fireEvent.keyDown(name, { key: '/' });
    expect(document.activeElement).toBe(name);
    const dialog = screen.getByRole('dialog');
    dialog.focus();
    fireEvent.keyDown(dialog, { key: '/' });
    expect(document.activeElement).toBe(search());
  });

  it('leaves Ctrl/Cmd+B to the browser', () => {
    render(<Harness />);
    const event = new KeyboardEvent('keydown', {
      key: 'b',
      ctrlKey: true,
      cancelable: true,
    });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it('keeps the form mounted when crossing the mobile breakpoint', () => {
    const setMobile = mockViewport(false);
    render(<Harness />);
    const input = document.getElementById('name-input');
    expect(screen.getByTestId('s-sidebar')).toBeInTheDocument();

    setMobile(true);
    expect(screen.queryByTestId('s-sidebar')).toBeNull();
    expect(screen.getByRole('tablist')).toHaveAttribute(
      'aria-orientation',
      'horizontal',
    );
    expect(document.getElementById('name-input')).toBe(input);
  });

  it('treats loading={false} as not loading', () => {
    render(
      <TooltipProvider>
        <SettingsDialog
          open
          onOpenChange={() => {}}
          title="Settings"
          onSubmit={onSubmit}
          sections={sections}
          testIdPrefix="s"
          loading={false}
        />
      </TooltipProvider>,
    );
    expect(document.getElementById('name-input')).toBeInTheDocument();
  });
});
