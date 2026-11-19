// @vitest-environment jsdom
import { zodResolver } from '@hookform/resolvers/zod';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { useForm, useFormContext } from 'react-hook-form';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { TooltipProvider } from '~/components/ui/tooltip';

const toastError = vi.hoisted(() => vi.fn());
vi.mock('sonner', () => ({ toast: { error: toastError, success: vi.fn() } }));

import { EventFormDialog, type EventFormTab } from '../EventFormDialog';
import { eventTabForField } from '../tabs';

// FormDialog renders a Radix ScrollArea, which jsdom cannot satisfy.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const schema = z.object({
  name: z.string().min(1, 'Name is required'),
  people_per_team: z.number().min(1, 'At least one'),
  min_mmr: z.number().min(0, 'Approval error'),
});
type Values = z.infer<typeof schema>;

const valid: Values = { name: 'Event', people_per_team: 5, min_mmr: 0 };

function NumberOrText({
  name,
  label,
  description,
}: {
  name: keyof Values;
  label: string;
  description?: string;
}) {
  const { control } = useFormContext<Values>();
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <input
              data-testid={`input-${name}`}
              value={field.value}
              onChange={(e) =>
                field.onChange(
                  typeof field.value === 'number'
                    ? Number(e.target.value)
                    : e.target.value,
                )
              }
            />
          </FormControl>
          {description && <FormDescription>{description}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

const defaultTabs: EventFormTab[] = [
  {
    value: 'event',
    content: (
      <div data-testid="panel-event">
        <NumberOrText name="name" label="Event Name" />
      </div>
    ),
  },
  {
    value: 'tournament',
    content: (
      <div data-testid="panel-tournament">
        <NumberOrText
          name="people_per_team"
          label="People Per Team"
          description="Players on each side"
        />
      </div>
    ),
  },
  {
    value: 'discord',
    lazy: true,
    content: <div data-testid="panel-discord" />,
  },
];

function Harness({
  open = true,
  values = valid,
  tabs = defaultTabs,
}: {
  open?: boolean;
  values?: Values;
  tabs?: EventFormTab[];
}) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: values,
  });
  return (
    <TooltipProvider>
      <EventFormDialog
        open={open}
        onOpenChange={() => {}}
        title="Test"
        submitLabel="Save"
        form={form}
        onValid={() => {}}
        isSubmitting={false}
        tabTestIdPrefix="test"
        tabs={tabs}
      />
    </TooltipProvider>
  );
}

const pick = (value: string) =>
  fireEvent.mouseDown(screen.getByTestId(`test-tab-${value}`), { button: 0 });

const panelOf = (testId: string) =>
  screen.getByTestId(testId).closest('[role="tabpanel"]');

const search = () => screen.getByTestId('test-settings-search');
const type = (q: string) =>
  fireEvent.change(search(), { target: { value: q } });
const isActive = (value: string) =>
  screen.getByTestId(`test-tab-${value}`).getAttribute('data-state') ===
  'active';

describe('EventFormDialog sections', () => {
  beforeEach(() => toastError.mockClear());

  it('lists sections as vertical tabs with prefixed testids, first one active', () => {
    render(<Harness />);
    expect(screen.getByRole('tablist')).toHaveAttribute(
      'aria-orientation',
      'vertical',
    );
    expect(isActive('event')).toBe(true);
    expect(screen.getByRole('tab', { name: /tournament/i })).toBe(
      screen.getByTestId('test-tab-tournament'),
    );
    expect(screen.getByTestId('test-tab-discord')).toBeInTheDocument();
  });

  it('keeps inactive non-lazy panels mounted but hidden', () => {
    render(<Harness />);
    expect(panelOf('panel-tournament')).toHaveAttribute('hidden');
    expect(panelOf('panel-event')).not.toHaveAttribute('hidden');
  });

  it('mounts a lazy panel on first visit and keeps it mounted', () => {
    render(<Harness />);
    expect(screen.queryByTestId('panel-discord')).toBeNull();
    pick('discord');
    expect(panelOf('panel-discord')).not.toHaveAttribute('hidden');
    pick('event');
    expect(panelOf('panel-discord')).toHaveAttribute('hidden');
  });

  it('resets to the first section when reopened', () => {
    const { rerender } = render(<Harness />);
    pick('discord');
    rerender(<Harness open={false} />);
    rerender(<Harness open />);
    expect(isActive('event')).toBe(true);
    expect(screen.queryByTestId('panel-discord')).toBeNull();
  });

  it('offers a section picker for small screens', () => {
    render(<Harness />);
    expect(screen.getByTestId('test-section-picker')).toHaveTextContent(
      'Event',
    );
  });
});

describe('EventFormDialog validation', () => {
  beforeEach(() => toastError.mockClear());

  it('switches to the section of the first invalid field and marks it', async () => {
    render(<Harness values={{ ...valid, people_per_team: 0 }} />);
    expect(screen.queryByTestId('test-tab-tournament-error')).toBeNull();
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(isActive('tournament')).toBe(true));
    expect(screen.getByTestId('test-tab-tournament-error')).toBeInTheDocument();
    expect(screen.queryByTestId('test-tab-event-error')).toBeNull();
    expect(screen.getByRole('tab', { name: /tournament.*error/i })).toBe(
      screen.getByTestId('test-tab-tournament'),
    );
    expect(toastError).toHaveBeenCalledWith(
      'Please fix the highlighted fields',
      { description: 'At least one' },
    );
  });

  it('marks every section with an error, not only the first', async () => {
    render(<Harness values={{ ...valid, name: '', people_per_team: 0 }} />);
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() =>
      expect(screen.getByTestId('test-tab-event-error')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('test-tab-tournament-error')).toBeInTheDocument();
  });

  it('clears the marker once the field is fixed', async () => {
    render(<Harness values={{ ...valid, people_per_team: 0 }} />);
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() =>
      expect(
        screen.getByTestId('test-tab-tournament-error'),
      ).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByTestId('input-people_per_team'), {
      target: { value: '4' },
    });
    await waitFor(() =>
      expect(screen.queryByTestId('test-tab-tournament-error')).toBeNull(),
    );
  });

  it('routes an error to the section the field renders in', async () => {
    // min_mmr belongs to Approval by default; here it renders under Event.
    const tabs: EventFormTab[] = [
      {
        value: 'event',
        content: <NumberOrText name="min_mmr" label="Minimum MMR" />,
      },
      { value: 'approval', content: <div data-testid="panel-approval" /> },
    ];
    render(<Harness tabs={tabs} values={{ ...valid, min_mmr: -1 }} />);
    pick('approval');
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(isActive('event')).toBe(true));
    expect(screen.getByTestId('test-tab-event-error')).toBeInTheDocument();
    expect(screen.queryByTestId('test-tab-approval-error')).toBeNull();
  });

  it('falls back to the first section when the mapped one is absent', async () => {
    render(<Harness values={{ ...valid, min_mmr: -1 }} />);
    pick('tournament');
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(isActive('event')).toBe(true);
  });
});

describe('EventFormDialog search', () => {
  afterEach(() => vi.useRealTimers());

  it('groups matches by section and dims sections without matches', () => {
    render(<Harness />);
    type('team');
    const tournament = screen.getByTestId('test-search-group-tournament');
    expect(tournament).not.toHaveAttribute('data-empty');
    expect(
      screen.getByTestId('test-search-result-people_per_team'),
    ).toHaveTextContent('People Per Team');
    expect(screen.getByTestId('test-search-group-event')).toHaveAttribute(
      'data-empty',
    );
    expect(screen.queryByRole('tablist')).toBeNull();
  });

  it('matches descriptions and fields of a lazy section not opened yet', () => {
    render(<Harness />);
    type('each side');
    expect(
      screen.getByTestId('test-search-result-people_per_team'),
    ).toBeInTheDocument();
    type('announcement');
    expect(
      screen.getByTestId('test-search-result-discord_announcement'),
    ).toBeInTheDocument();
  });

  it('says so when nothing matches', () => {
    render(<Harness />);
    type('zzzz');
    expect(screen.getByTestId('test-search-empty')).toHaveTextContent('zzzz');
  });

  it('jumps to a picked field: switches section, highlights, focuses, clears', () => {
    vi.useFakeTimers();
    render(<Harness />);
    type('people');
    fireEvent.click(screen.getByTestId('test-search-result-people_per_team'));
    expect(isActive('tournament')).toBe(true);
    const input = screen.getByTestId('input-people_per_team');
    const row = input.closest('[data-field]');
    expect(row).toHaveAttribute('data-search-hit');
    expect(input).toHaveFocus();
    expect(search()).toHaveValue('');
    expect(screen.getByRole('tablist')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(2500));
    expect(row).not.toHaveAttribute('data-search-hit');
  });

  it('opens a lazy section when its result is picked', () => {
    render(<Harness />);
    type('announcement');
    fireEvent.click(
      screen.getByTestId('test-search-result-discord_announcement'),
    );
    expect(isActive('discord')).toBe(true);
    expect(panelOf('panel-discord')).not.toHaveAttribute('hidden');
  });

  it('moves through results with the arrow keys and picks with Enter', () => {
    render(<Harness />);
    type('e');
    const input = search();
    const options = screen.getAllByRole('option');
    expect(options.length).toBeGreaterThan(1);
    expect(input).toHaveAttribute('aria-activedescendant', options[0].id);
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input).toHaveAttribute('aria-activedescendant', options[1].id);
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(input).toHaveAttribute(
      'aria-activedescendant',
      options[options.length - 1].id,
    );
    fireEvent.keyDown(input, { key: 'Home' });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    const second = options[1].getAttribute('data-testid');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(second).toBe('test-search-result-people_per_team');
    expect(isActive('tournament')).toBe(true);
  });

  it('clear button restores the section list', () => {
    render(<Harness />);
    type('people');
    fireEvent.click(screen.getByRole('button', { name: /clear search/i }));
    expect(search()).toHaveValue('');
    expect(screen.getByRole('tablist')).toBeInTheDocument();
  });

  it('does not put the cursor in search when the dialog opens', () => {
    render(<Harness />);
    expect(search()).not.toHaveFocus();
    expect(screen.getByRole('dialog')).toHaveFocus();
  });

  it('focuses search on "/" outside a text field and on Ctrl/Cmd+K', () => {
    render(<Harness />);
    const name = screen.getByTestId('input-name');
    name.focus();
    fireEvent.keyDown(name, { key: '/' });
    expect(name).toHaveFocus();
    name.blur();
    fireEvent.keyDown(document.body, { key: '/' });
    expect(search()).toHaveFocus();
    name.focus();
    fireEvent.keyDown(name, { key: 'k', ctrlKey: true });
    expect(search()).toHaveFocus();
    name.focus();
    fireEvent.keyDown(name, { key: 'k', metaKey: true });
    expect(search()).toHaveFocus();
  });
});

describe('eventTabForField', () => {
  it.each([
    ['name', 'event'],
    ['timezone', 'event'],
    ['discord_notify_new_events', 'discord'],
    ['discord_send_lobby_info', 'lobby'],
    ['dota_lobby_password', 'lobby'],
    ['game_mode', 'lobby'],
    ['draft_grace_time_s', 'tournament'],
    ['tournament_league', 'tournament'],
    ['min_mmr', 'approval'],
    ['discord_require_rank_screenshot', 'approval'],
    ['discord_announcement_hours', 'discord'],
    ['some_future_discord_flag', 'event'],
    ['discord_some_future_flag', 'discord'],
  ])('%s → %s', (field, tab) => {
    expect(eventTabForField(field)).toBe(tab);
  });
});
