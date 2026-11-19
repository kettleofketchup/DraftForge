// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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
    keywords: ['password'],
    content: (
      <div>
        <h3>Dota Lobbies</h3>
        <label htmlFor="region-input">Lobby region</label>
        <input id="region-input" />
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

describe('SettingsDialog', () => {
  beforeEach(() => onSubmit.mockClear());

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

  it('filters categories by name and keywords', () => {
    render(<Harness />);
    type('channel');
    expect(navItem('discord')).toBeInTheDocument();
    expect(navItem('general')).toBeNull();
    expect(navItem('lobby')).toBeNull();
  });

  it('lists matching field labels and headings under their category', () => {
    render(<Harness />);
    type('lobb');
    const hits = screen
      .getAllByTestId('s-search-hit')
      .map((h) => h.textContent);
    expect(hits).toEqual(['Dota Lobbies', 'Lobby region']);
    expect(navItem('lobby')).toBeInTheDocument();
    expect(navItem('general')).toBeNull();
  });

  it('matches every search term, in any order', () => {
    render(<Harness />);
    type('region lobby');
    expect(
      screen.getAllByTestId('s-search-hit').map((h) => h.textContent),
    ).toEqual(['Lobby region']);
  });

  it('jumps to a hit: selects its category and focuses its control', async () => {
    render(<Harness />);
    type('region');
    fireEvent.click(screen.getByTestId('s-search-hit'));
    expect(navItem('lobby')).toHaveAttribute('data-state', 'active');
    await new Promise((r) => requestAnimationFrame(r));
    expect(document.activeElement).toBe(
      document.getElementById('region-input'),
    );
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
    expect(navItem('general')).toBeInTheDocument();
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
    expect(screen.getByTestId('s-search-hit')).toHaveTextContent(
      'Announcement channel',
    );
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

  it('"/" focuses the search box', () => {
    render(<Harness />);
    fireEvent.keyDown(document.body, { key: '/' });
    expect(document.activeElement).toBe(search());
  });
});
