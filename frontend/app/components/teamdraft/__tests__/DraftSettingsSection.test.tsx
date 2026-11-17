// @vitest-environment jsdom
import { zodResolver } from '@hookform/resolvers/zod';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { Form } from '~/components/ui/form';
import { DraftSettingsSection } from '../DraftSettingsSection';
import {
  DraftSettingsFormSchema,
  draftSettingsFormToEventFields,
  draftSettingsFormToPatch,
  draftSettingsToFormInput,
  eventFieldsToDraftSettingsFormInput,
} from '../schemas';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const HarnessSchema = DraftSettingsFormSchema.extend({
  draft_type: z.string(),
});
type HarnessOutput = z.output<typeof HarnessSchema>;

function Harness({
  onSubmit,
  defaults = {},
  showOptional = true,
}: {
  onSubmit: (v: HarnessOutput) => void;
  defaults?: Partial<z.input<typeof HarnessSchema>>;
  showOptional?: boolean;
}) {
  const form = useForm<z.input<typeof HarnessSchema>, unknown, HarnessOutput>({
    resolver: zodResolver(HarnessSchema),
    defaultValues: {
      draft_type: 'snake',
      ...draftSettingsToFormInput(null),
      ...defaults,
    },
  });
  return (
    <Form {...form}>
      <form data-testid="harness" onSubmit={form.handleSubmit(onSubmit)}>
        <DraftSettingsSection
          control={form.control}
          showDraftType={showOptional}
          showTimeoutAction={showOptional}
        />
      </form>
    </Form>
  );
}

const submit = () => fireEvent.submit(screen.getByTestId('harness'));

describe('DraftSettingsSection', () => {
  it('renders every control with defaults in seconds', () => {
    render(<Harness onSubmit={vi.fn()} />);
    expect(screen.getByTestId('draft-settings-draft-type')).toBeInTheDocument();
    expect(screen.getByTestId('draft-settings-team-grace-s')).toHaveValue(30);
    expect(screen.getByTestId('draft-settings-team-reserve-s')).toHaveValue(30);
    expect(
      screen.getByTestId('draft-settings-team-timeout-action'),
    ).toHaveTextContent('Skip turn');
    expect(screen.getByTestId('draft-settings-hero-grace-s')).toHaveValue(30);
    expect(screen.getByTestId('draft-settings-hero-reserve-s')).toHaveValue(90);
  });

  it('hides the team timer inputs when the team timer is off', () => {
    render(<Harness onSubmit={vi.fn()} />);
    fireEvent.click(screen.getByTestId('draft-settings-team-timer-enabled'));
    expect(screen.queryByTestId('draft-settings-team-grace-s')).toBeNull();
    expect(screen.queryByTestId('draft-settings-team-reserve-s')).toBeNull();
    expect(
      screen.queryByTestId('draft-settings-team-timeout-action'),
    ).toBeNull();
    expect(
      screen.getByTestId('draft-settings-hero-grace-s'),
    ).toBeInTheDocument();
  });

  it('hides the hero timer inputs when the hero timer is off', () => {
    render(<Harness onSubmit={vi.fn()} />);
    fireEvent.click(screen.getByTestId('draft-settings-hero-timer-enabled'));
    expect(screen.queryByTestId('draft-settings-hero-grace-s')).toBeNull();
    expect(screen.queryByTestId('draft-settings-hero-reserve-s')).toBeNull();
    expect(
      screen.getByTestId('draft-settings-team-grace-s'),
    ).toBeInTheDocument();
  });

  it('submits edited seconds and converts them to ms', async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId('draft-settings-team-grace-s'), {
      target: { value: '45' },
    });
    fireEvent.change(screen.getByTestId('draft-settings-hero-reserve-s'), {
      target: { value: '120' },
    });
    fireEvent.click(screen.getByTestId('draft-settings-team-timer-enabled'));
    submit();
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const values = onSubmit.mock.calls[0][0] as HarnessOutput;
    expect(draftSettingsFormToPatch(values)).toEqual({
      timer_enabled: false,
      grace_time_ms: 45000,
      reserve_time_ms: 30000,
      hero_timer_enabled: true,
      hero_grace_time_ms: 30000,
      hero_reserve_time_ms: 120000,
    });
  });

  it('hides the draft type and timeout action when asked', () => {
    render(<Harness onSubmit={vi.fn()} showOptional={false} />);
    expect(screen.queryByTestId('draft-settings-draft-type')).toBeNull();
    expect(
      screen.queryByTestId('draft-settings-team-timeout-action'),
    ).toBeNull();
    expect(
      screen.getByTestId('draft-settings-team-grace-s'),
    ).toBeInTheDocument();
  });

  it('drops an invalid hidden value when the timer is turned off', async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId('draft-settings-hero-grace-s'), {
      target: { value: '' },
    });
    fireEvent.click(screen.getByTestId('draft-settings-hero-timer-enabled'));
    submit();
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const values = onSubmit.mock.calls[0][0] as HarnessOutput;
    expect(values.hero_timer_enabled).toBe(false);
    expect(values.hero_grace_time_s).toBe(30);
  });

  it('blocks submit on an invalid visible value', async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    fireEvent.change(screen.getByTestId('draft-settings-team-grace-s'), {
      target: { value: '0' },
    });
    submit();
    expect(await screen.findByText('At least 1 second')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe('draft settings conversion', () => {
  it('reads tournament draft_options in ms as seconds', () => {
    expect(
      draftSettingsToFormInput({
        timer_enabled: false,
        grace_time_ms: 20000,
        reserve_time_ms: 0,
        timeout_action: 'skip_turn',
        hero_timer_enabled: false,
        hero_grace_time_ms: 15000,
        hero_reserve_time_ms: 60000,
      }),
    ).toEqual({
      draft_timer_enabled: false,
      draft_grace_time_s: 20,
      draft_reserve_time_s: 0,
      draft_timeout_action: 'skip_turn',
      hero_timer_enabled: false,
      hero_grace_time_s: 15,
      hero_reserve_time_s: 60,
    });
  });

  it('defaults missing hero keys from an older payload', () => {
    const v = draftSettingsToFormInput({
      timer_enabled: true,
      grace_time_ms: 10000,
      reserve_time_ms: 5000,
      timeout_action: 'skip_turn',
    });
    expect(v.hero_timer_enabled).toBe(true);
    expect(v.hero_grace_time_s).toBe(30);
    expect(v.hero_reserve_time_s).toBe(90);
  });

  it('round-trips flat event fields', () => {
    const fields = {
      draft_timer_enabled: true,
      draft_grace_time_ms: 25000,
      draft_reserve_time_ms: 40000,
      draft_timeout_action: 'skip_turn' as const,
      hero_timer_enabled: false,
      hero_grace_time_ms: 35000,
      hero_reserve_time_ms: 100000,
    };
    const form = DraftSettingsFormSchema.parse(
      eventFieldsToDraftSettingsFormInput(fields),
    );
    expect(draftSettingsFormToEventFields(form)).toEqual(fields);
  });
});
