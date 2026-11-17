// @vitest-environment jsdom
import { zodResolver } from '@hookform/resolvers/zod';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
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

function Harness({
  open = true,
  values = valid,
  tabs,
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
        tabs={
          tabs ?? [
            { value: 'event', content: <div data-testid="panel-event" /> },
            {
              value: 'tournament',
              content: <div data-testid="panel-tournament" />,
            },
            {
              value: 'discord',
              lazy: true,
              content: <div data-testid="panel-discord" />,
            },
          ]
        }
      />
    </TooltipProvider>
  );
}

const pick = (value: string) =>
  fireEvent.mouseDown(screen.getByTestId(`test-tab-${value}`), { button: 0 });

const panelOf = (testId: string) =>
  screen.getByTestId(testId).closest('[role="tabpanel"]');

describe('EventFormDialog', () => {
  beforeEach(() => toastError.mockClear());

  it('prefixes trigger testids and starts on the first tab', () => {
    render(<Harness />);
    expect(screen.getByTestId('test-tab-event')).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.getByTestId('test-tab-tournament')).toBeInTheDocument();
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

  it('switches to the tab of the first invalid field', async () => {
    render(<Harness values={{ ...valid, people_per_team: 0 }} />);
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() =>
      expect(screen.getByTestId('test-tab-tournament')).toHaveAttribute(
        'data-state',
        'active',
      ),
    );
    expect(toastError).toHaveBeenCalledWith(
      'Please fix the highlighted fields',
      { description: 'At least one' },
    );
  });

  it('falls back to the first tab when the mapped tab is absent', async () => {
    render(<Harness values={{ ...valid, min_mmr: -1 }} />);
    pick('tournament');
    fireEvent.click(screen.getByTestId('form-dialog-submit'));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(screen.getByTestId('test-tab-event')).toHaveAttribute(
      'data-state',
      'active',
    );
  });

  it('resets to the first tab when reopened', () => {
    const { rerender } = render(<Harness />);
    pick('discord');
    rerender(<Harness open={false} />);
    rerender(<Harness open />);
    expect(screen.getByTestId('test-tab-event')).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.queryByTestId('panel-discord')).toBeNull();
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
  ])('%s → %s', (field, tab) => {
    expect(eventTabForField(field)).toBe(tab);
  });
});
