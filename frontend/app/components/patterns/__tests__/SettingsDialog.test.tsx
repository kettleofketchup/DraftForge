// @vitest-environment jsdom
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { createRef, useState, type Ref } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import {
  SettingsDialog,
  type SettingsDialogHandle,
  type SettingsSection,
} from '../SettingsDialog';

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

function Harness({
  items = sections,
  sectionRef,
  prefix = 's',
  open = true,
}: {
  items?: SettingsSection[];
  sectionRef?: Ref<SettingsDialogHandle>;
  prefix?: string;
  open?: boolean;
}) {
  return (
    <TooltipProvider>
      <SettingsDialog
        open={open}
        onOpenChange={() => {}}
        title="Settings"
        onSubmit={onSubmit}
        sections={items}
        testIdPrefix={prefix}
        sectionRef={sectionRef}
      />
    </TooltipProvider>
  );
}

function Collapsed() {
  const [expanded, setExpanded] = useState(false);
  return (
    <div data-fields="secret">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded(true)}
      >
        More options
      </button>
      {expanded && (
        <div data-field="secret">
          <label htmlFor="secret-input">Secret</label>
          <input id="secret-input" />
        </div>
      )}
    </div>
  );
}

const nameRow = (id: string) => (
  <div data-field="name">
    <label htmlFor={id}>Name</label>
    <input id={id} />
  </div>
);

const revealSections: SettingsSection[] = [
  {
    value: 'general',
    label: 'General',
    content: (
      <div>
        <label htmlFor="title-input">Title</label>
        <input id="title-input" />
      </div>
    ),
  },
  {
    value: 'schedule',
    label: 'Schedule',
    content: (
      <div data-field="frequency">
        <label htmlFor="frequency-input">Frequency</label>
        <input id="frequency-input" />
      </div>
    ),
  },
  {
    value: 'advanced',
    label: 'Advanced',
    content: <Collapsed />,
  },
  {
    value: 'discord',
    label: 'Discord',
    lazy: true,
    fields: { channel: { label: 'Announcement channel' } },
    content: (
      <div data-field="channel">
        <label htmlFor="channel-input">Announcement channel</label>
        <input id="channel-input" />
      </div>
    ),
  },
];

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

  it('lists same-named fields from different sections separately', () => {
    const tz = (label: string) => (
      <div data-field="timezone">
        <label htmlFor={label}>{label}</label>
        <input id={label} />
      </div>
    );
    render(
      <Harness
        items={[
          { value: 'general', label: 'General', content: tz('Org timezone') },
          {
            value: 'defaults',
            label: 'Defaults',
            content: tz('Event timezone'),
            fields: { timezone: { label: 'Event timezone' } },
          },
        ]}
      />,
    );
    // Only the active panel is mounted until visited; visit both.
    fireEvent.click(screen.getByTestId('s-tab-defaults'));
    fireEvent.click(screen.getByTestId('s-tab-general'));
    type('timezone');
    expect(hitLabels().sort()).toEqual(['Event timezone', 'Org timezone']);
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
    expect(search()).toHaveValue('region');
  });

  describe('imperative field reveal', () => {
    it('reveals a lazy field and clears stale programmatic search', async () => {
      const ref = createRef<SettingsDialogHandle>();
      render(<Harness items={revealSections} sectionRef={ref} />);
      const title = screen.getByLabelText('Title');
      fireEvent.change(title, { target: { value: 'Unsaved title' } });
      expect(screen.queryByLabelText('Announcement channel')).toBeNull();
      type('no matching setting');

      act(() => ref.current!.revealField('channel', 'general'));

      expect(navItem('discord')).toHaveAttribute('data-state', 'active');
      expect(search()).toHaveValue('');
      await waitFor(() =>
        expect(screen.getByLabelText('Announcement channel')).toHaveFocus(),
      );
      expect(
        screen.getByLabelText('Announcement channel').closest('[data-field]'),
      ).toHaveAttribute('data-search-hit');
      act(() => ref.current!.selectSection('general'));
      expect(screen.getByLabelText('Title')).toBe(title);
      expect(title).toHaveValue('Unsaved title');
    });

    it('expands a collapsed field', async () => {
      const ref = createRef<SettingsDialogHandle>();
      render(<Harness items={revealSections} sectionRef={ref} />);

      act(() => ref.current!.revealField('secret', 'advanced'));

      expect(navItem('advanced')).toHaveAttribute('data-state', 'active');
      await waitFor(() =>
        expect(screen.getByLabelText('Secret')).toHaveFocus(),
      );
      expect(
        screen.getByLabelText('Secret').closest('[data-field]'),
      ).toHaveAttribute('data-search-hit');
      expect(
        screen.getByRole('button', { name: 'More options' }),
      ).toHaveAttribute('aria-expanded', 'true');
    });

    it('prefers rendered ownership over fallback', async () => {
      const ref = createRef<SettingsDialogHandle>();
      const items = revealSections.map((section) =>
        section.value === 'discord'
          ? { ...section, fields: { frequency: { label: 'Frequency' } } }
          : section,
      );
      render(<Harness items={items} sectionRef={ref} />);

      act(() => ref.current!.revealField('frequency', 'general'));

      expect(navItem('schedule')).toHaveAttribute('data-state', 'active');
      await waitFor(() =>
        expect(screen.getByLabelText('Frequency')).toHaveFocus(),
      );
      expect(
        screen.getByLabelText('Frequency').closest('[data-field]'),
      ).toHaveAttribute('data-search-hit');
    });

    it('does not focus another settings instance', async () => {
      const ref = createRef<SettingsDialogHandle>();
      render(
        <>
          <Harness
            prefix="other"
            items={[
              {
                value: 'general',
                label: 'General',
                content: nameRow('other-name'),
              },
            ]}
          />
          <Harness
            sectionRef={ref}
            items={[
              { value: 'general', label: 'General', content: <p>General</p> },
              {
                value: 'details',
                label: 'Details',
                content: nameRow('own-name'),
              },
            ]}
          />
        </>,
      );

      act(() => ref.current!.revealField('name', 'general'));

      expect(navItem('details')).toHaveAttribute('data-state', 'active');
      await waitFor(() =>
        expect(document.getElementById('own-name')).toHaveFocus(),
      );
      expect(
        document.getElementById('own-name')!.closest('[data-field]'),
      ).toHaveAttribute('data-search-hit');
      expect(
        document.getElementById('other-name')!.closest('[data-field]'),
      ).not.toHaveAttribute('data-search-hit');
    });

    it('focuses the panel for an unresolved row', async () => {
      const ref = createRef<SettingsDialogHandle>();
      render(<Harness items={revealSections} sectionRef={ref} />);

      act(() => ref.current!.revealField('missing', 'schedule'));

      expect(navItem('schedule')).toHaveAttribute('data-state', 'active');
      const panel = screen.getByRole('tabpanel', { name: 'Schedule' });
      await waitFor(() => expect(panel).toHaveFocus());
      expect(panel).toHaveAttribute('data-search-hit');
    });

    it('ignores an unknown fallback section', async () => {
      const ref = createRef<SettingsDialogHandle>();
      render(<Harness items={revealSections} sectionRef={ref} />);
      type('Title');
      search().focus();

      act(() => ref.current!.revealField('missing', 'removed'));
      await frame();

      expect(navItem('general')).toHaveAttribute('data-state', 'active');
      expect(search()).toHaveValue('Title');
      expect(search()).toHaveFocus();
    });

    it('does nothing through a closed or unmounted handle', async () => {
      const ref = createRef<SettingsDialogHandle>();
      const onSectionChange = vi.fn();
      const dialog = (open: boolean) => (
        <TooltipProvider>
          <SettingsDialog
            open={open}
            onOpenChange={() => {}}
            title="Settings"
            onSubmit={onSubmit}
            sections={revealSections}
            testIdPrefix="s"
            sectionRef={ref}
            onSectionChange={onSectionChange}
          />
        </TooltipProvider>
      );
      const view = render(dialog(true));
      view.rerender(dialog(false));

      act(() => ref.current!.revealField('channel', 'discord'));
      await frame();
      expect(onSectionChange).not.toHaveBeenCalled();

      view.rerender(dialog(true));
      const handle = ref.current!;
      view.unmount();
      act(() => handle.revealField('channel', 'discord'));
      await frame();
      expect(onSectionChange).not.toHaveBeenCalled();
    });
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

  describe('groups, footer and controlled section', () => {
    const grouped: SettingsSection[] = [
      { value: 'a', label: 'Alpha', group: 'Organization', content: <p>a</p> },
      { value: 'b', label: 'Beta', group: 'Organization', content: <p>b</p> },
      {
        value: 'c',
        label: 'Gamma',
        group: 'New Event Defaults',
        content: <p>c</p>,
      },
    ];

    it('renders a labelled sidebar group per section group, in first-appearance order', () => {
      render(<Harness items={grouped} />);
      expect(screen.getByText('Organization')).toBeInTheDocument();
      expect(screen.getByText('New Event Defaults')).toBeInTheDocument();
      const groups = document.querySelectorAll('[data-sidebar="group"]');
      expect(groups[0]).toHaveTextContent('Organization');
      expect(groups[1]).toHaveTextContent('New Event Defaults');
      expect(groups[1].contains(navItem('c'))).toBe(true);
      expect(groups[0].contains(navItem('c'))).toBe(false);
    });

    it('puts each group in a labelled role=group and no loose text in the tablist', () => {
      render(<Harness items={grouped} />);
      const tablist = screen.getByRole('tablist');
      const groups = within(tablist).getAllByRole('group');
      expect(groups).toHaveLength(2);
      expect(groups.map((g) => g.parentElement)).toEqual([tablist, tablist]);
      expect(tablist.children).toHaveLength(2);
      for (const node of Array.from(tablist.childNodes)) {
        expect(node.nodeType).toBe(Node.ELEMENT_NODE);
      }
      expect(
        groups.map((g) =>
          document
            .getElementById(g.getAttribute('aria-labelledby') ?? '')
            ?.textContent?.trim(),
        ),
      ).toEqual(['Organization', 'New Event Defaults']);
      expect(within(groups[0]).getAllByRole('tab')).toHaveLength(2);
      expect(within(groups[1]).getAllByRole('tab')).toHaveLength(1);
    });

    it('ArrowDown from the last tab of one group focuses the first tab of the next', async () => {
      render(<Harness items={grouped} />);
      navItem('b')?.focus();
      fireEvent.keyDown(navItem('b') as HTMLElement, { key: 'ArrowDown' });
      await waitFor(() => expect(navItem('c')).toHaveFocus());
      fireEvent.keyDown(navItem('c') as HTMLElement, { key: 'ArrowUp' });
      await waitFor(() => expect(navItem('b')).toHaveFocus());
    });

    it('search hit names the group for grouped sections', () => {
      render(
        <Harness
          items={[
            {
              value: 'd1',
              label: 'Discord',
              group: 'Organization',
              content: <label>Server</label>,
            },
            {
              value: 'd2',
              label: 'Discord',
              group: 'New Event Defaults',
              content: <label>Server</label>,
            },
          ]}
        />,
      );
      type('server');
      const subtitles = screen
        .getAllByTestId('s-search-hit')
        .map((h) => h.querySelectorAll('span')[1]?.textContent);
      expect(subtitles).toEqual([
        'Discord · Organization',
        'Discord · New Event Defaults',
      ]);
    });

    it('opens on the controlled section and reports changes', () => {
      const onSectionChange = vi.fn();
      render(
        <TooltipProvider>
          <SettingsDialog
            open
            onOpenChange={() => {}}
            title="Settings"
            onSubmit={onSubmit}
            sections={grouped}
            testIdPrefix="x"
            section="b"
            onSectionChange={onSectionChange}
          />
        </TooltipProvider>,
      );
      expect(screen.getByTestId('x-tab-b')).toHaveAttribute(
        'data-state',
        'active',
      );
      fireEvent.mouseDown(screen.getByTestId('x-tab-c'), { button: 0 });
      expect(onSectionChange).toHaveBeenCalledWith('c');
    });

    it('renders footer below panels', () => {
      render(
        <TooltipProvider>
          <SettingsDialog
            open
            onOpenChange={() => {}}
            title="Settings"
            onSubmit={onSubmit}
            sections={grouped}
            testIdPrefix="s"
            footer={<div data-testid="foot" />}
          />
        </TooltipProvider>,
      );
      expect(screen.getByTestId('foot')).toBeInTheDocument();
    });

    it('renders group headings above each group tab strip on mobile', () => {
      mockViewport(true);
      render(<Harness items={grouped} />);
      const lists = screen.getAllByRole('tablist');
      expect(lists).toHaveLength(2);
      const org = screen.getByText('Organization');
      const defaults = screen.getByText('New Event Defaults');
      expect(org.tagName).toBe('P');
      expect(
        org.compareDocumentPosition(lists[0]) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(
        defaults.compareDocumentPosition(lists[1]) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    });
  });
});
