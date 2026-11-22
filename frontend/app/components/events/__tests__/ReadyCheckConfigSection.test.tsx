// @vitest-environment jsdom
import { zodResolver } from '@hookform/resolvers/zod';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useForm, type Resolver, type UseFormReturn } from 'react-hook-form';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import { Form } from '~/components/ui/form';
import { ReadyCheckConfigSection } from '../ReadyCheckConfigSection';
import { READY_CHECK_TEST_IDS as IDS } from '../form/testIds';
import {
  READY_CHECK_CONFIG_DEFAULTS,
  readyCheckConfigSchema,
  refineReadyCheck,
  type ReadyCheckFields,
} from '../schemas';

vi.mock('../DiscordChannelPicker', () => ({
  DiscordChannelPicker: (props: {
    kind?: string;
    organizationId: number;
    'data-testid'?: string;
  }) => (
    <div
      data-testid={props['data-testid']}
      data-kind={props.kind}
      data-org={props.organizationId}
    />
  ),
}));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

let form: UseFormReturn<ReadyCheckFields>;

function Harness({
  initial,
  organizationId,
  showAutoConfirm,
}: {
  initial?: Partial<ReadyCheckFields>;
  organizationId: number | null;
  showAutoConfirm?: boolean;
}) {
  form = useForm<ReadyCheckFields>({
    resolver: zodResolver(
      readyCheckConfigSchema.superRefine((v, ctx) => refineReadyCheck(v, ctx)),
    ) as Resolver<ReadyCheckFields>,
    defaultValues: { ...READY_CHECK_CONFIG_DEFAULTS, ...initial },
  });
  return (
    <Form {...form}>
      <ReadyCheckConfigSection
        control={form.control}
        setValue={form.setValue}
        organizationId={organizationId}
        showAutoConfirm={showAutoConfirm}
      />
    </Form>
  );
}

function renderSection(
  props: Partial<Parameters<typeof Harness>[0]> = {},
): void {
  render(<Harness organizationId={7} {...props} />);
}

const click = (id: string): void => {
  fireEvent.click(screen.getByTestId(id));
};

const type = (id: string, value: string): void => {
  fireEvent.change(screen.getByTestId(id), { target: { value } });
};

const validate = async (): Promise<void> => {
  await act(async () => {
    await form.trigger();
  });
};

describe('ReadyCheckConfigSection', () => {
  it('toggle on applies the automatic preset', () => {
    renderSection({ initial: { auto_confirm: true } });
    click(IDS.toggle);
    expect(form.getValues('roll_call_enabled')).toBe(true);
    expect(form.getValues('roll_call_mode')).toBe('automatic');
    expect(form.getValues('auto_confirm')).toBe(false);
    expect(form.getFieldState('roll_call_enabled').isDirty).toBe(true);
  });

  it('toggle off only clears roll_call_enabled', () => {
    renderSection({
      initial: {
        roll_call_enabled: true,
        roll_call_mode: 'automatic',
        ready_check_open_minutes: 90,
      },
    });
    click(IDS.toggle);
    expect(form.getValues('roll_call_enabled')).toBe(false);
    expect(form.getValues('roll_call_mode')).toBe('automatic');
    expect(form.getValues('ready_check_open_minutes')).toBe(90);
  });

  it('keeps a saved Staff-verified mode when switched off and on again', () => {
    renderSection({
      initial: { roll_call_enabled: true, roll_call_mode: 'manual' },
    });
    click(IDS.toggle);
    click(IDS.toggle);
    expect(form.getValues('roll_call_enabled')).toBe(true);
    expect(form.getValues('roll_call_mode')).toBe('manual');
  });

  it('describes Staff-verified mode without automatic drops', () => {
    renderSection({
      initial: { roll_call_enabled: true, roll_call_mode: 'manual' },
    });
    const section = screen.getByTestId(IDS.section);
    expect(section).toHaveTextContent('nobody is dropped automatically');
    expect(section).not.toHaveTextContent('later release');
  });

  it('says automatic drops arrive in a later release', () => {
    renderSection();
    click(IDS.toggle);
    const section = screen.getByTestId(IDS.section);
    expect(section).toHaveTextContent('later release');
    expect(section).not.toHaveTextContent('unconfirmed members are dropped.');
  });

  it('shows an existing manual check as Staff-verified', () => {
    renderSection({
      initial: { roll_call_enabled: true, roll_call_mode: 'manual' },
    });
    expect(screen.getByTestId(IDS.toggle)).toHaveAttribute(
      'data-state',
      'checked',
    );
    click(IDS.settingsTrigger);
    expect(screen.getByTestId(IDS.mode)).toHaveTextContent('Staff-verified');
  });

  it('starts with settings and voice collapsed', () => {
    renderSection({ initial: { roll_call_enabled: true } });
    expect(screen.queryByTestId(IDS.open)).not.toBeInTheDocument();
    expect(screen.queryByTestId(IDS.voiceConfirms)).not.toBeInTheDocument();
    click(IDS.voiceTrigger);
    expect(screen.getByTestId(IDS.voiceConfirms)).toBeInTheDocument();
  });

  it('names who gets each message', () => {
    renderSection({ initial: { roll_call_enabled: true } });
    click(IDS.settingsTrigger);
    const section = screen.getByTestId(IDS.section);
    expect(section).toHaveTextContent(
      'Nudge unconfirmed members by DM (minutes)',
    );
    expect(section).toHaveTextContent(
      'Ops notice per unconfirmed member (minutes)',
    );
    expect(section).toHaveTextContent('Shown to org and league staff');
    expect(section).toHaveTextContent(
      'DM members on their first sign-up that confirmation is mandatory',
    );
    expect(section).toHaveTextContent('DM members who are dropped');
  });

  it('says the ready check and start cull are not active yet', () => {
    renderSection({ initial: { roll_call_enabled: true } });
    click(IDS.settingsTrigger);
    click(IDS.voiceTrigger);
    expect(screen.getByTestId(IDS.settingsNotActive)).toHaveTextContent(
      'Not active yet',
    );
    expect(screen.getByTestId(IDS.voiceNotActive)).toHaveTextContent(
      'Not active yet',
    );
  });

  it('reads the low-completion row as a sentence', () => {
    renderSection({ initial: { roll_call_enabled: true } });
    click(IDS.settingsTrigger);
    const row = screen.getByTestId(`${IDS.minCompletion}-row`);
    expect(row).toHaveTextContent('If fewer than 70% have confirmed at close');
    expect(screen.getByTestId(IDS.lowCompletionAction)).toHaveTextContent(
      'Make the check non-binding (drop nobody)',
    );
  });

  it('disables auto-confirm while the check is on', () => {
    renderSection({ showAutoConfirm: true });
    const autoConfirm = screen.getByTestId(IDS.autoConfirm);
    expect(autoConfirm).toBeEnabled();
    click(IDS.toggle);
    expect(screen.getByTestId(IDS.autoConfirm)).toBeDisabled();
    expect(
      screen.getByText('Off while confirmation is mandatory'),
    ).toBeInTheDocument();
  });

  it('hides auto-confirm without showAutoConfirm', () => {
    renderSection();
    expect(screen.queryByTestId(IDS.autoConfirm)).not.toBeInTheDocument();
  });

  it('chase off stores null and turning it back restores 30', () => {
    renderSection({
      initial: { roll_call_enabled: true, ready_check_chase_minutes: 45 },
    });
    click(IDS.settingsTrigger);
    click(IDS.chaseOff);
    expect(form.getValues('ready_check_chase_minutes')).toBeNull();
    expect(screen.getByTestId(IDS.chase)).toBeDisabled();
    click(IDS.chaseOff);
    expect(form.getValues('ready_check_chase_minutes')).toBe(30);
  });

  it('renders a disabled text input without an organization', () => {
    renderSection({ organizationId: null });
    click(IDS.voiceTrigger);
    const input = screen.getByTestId(IDS.voiceChannel);
    expect(input.tagName).toBe('INPUT');
    expect(input).toBeDisabled();
  });

  it('renders the voice picker for an organization', () => {
    renderSection({ organizationId: 7 });
    click(IDS.voiceTrigger);
    const picker = screen.getByTestId(IDS.voiceChannel);
    expect(picker).toHaveAttribute('data-kind', 'voice');
    expect(picker).toHaveAttribute('data-org', '7');
  });
  it('resets an invalid Opens value when the settings collapse', () => {
    renderSection({ initial: { roll_call_enabled: true } });
    click(IDS.settingsTrigger);
    type(IDS.open, '0');
    expect(form.getValues('ready_check_open_minutes')).toBe(0);
    click(IDS.settingsTrigger);
    expect(form.getValues('ready_check_open_minutes')).toBe(120);
  });

  it('resets an empty Opens value when the settings collapse', () => {
    renderSection({ initial: { roll_call_enabled: true } });
    click(IDS.settingsTrigger);
    type(IDS.open, '');
    click(IDS.settingsTrigger);
    expect(form.getValues('ready_check_open_minutes')).toBe(120);
  });

  it('resets cross-field invalid timings when the check is switched off', () => {
    renderSection({ initial: { roll_call_enabled: true } });
    click(IDS.settingsTrigger);
    type(IDS.open, '20');
    type(IDS.close, '30');
    click(IDS.toggle);
    expect(form.getValues('ready_check_open_minutes')).toBe(120);
    expect(form.getValues('ready_check_close_minutes')).toBe(10);
  });

  it('keeps valid timings when the check is switched off', () => {
    renderSection({ initial: { roll_call_enabled: true } });
    click(IDS.settingsTrigger);
    type(IDS.open, '90');
    click(IDS.toggle);
    expect(form.getValues('ready_check_open_minutes')).toBe(90);
  });

  it('disables the cull minutes while the cull is off', () => {
    renderSection();
    click(IDS.voiceTrigger);
    expect(screen.getByTestId(IDS.cullMinutes)).toBeDisabled();
    click(IDS.cullEnabled);
    expect(screen.getByTestId(IDS.cullMinutes)).toBeEnabled();
  });

  it('shows the R6 error under the voice presence switch', async () => {
    renderSection();
    click(IDS.voiceTrigger);
    click(IDS.voiceConfirms);
    await validate();
    expect(
      screen.getByText('Voice presence confirms need an event voice channel.'),
    ).toBeVisible();
  });

  it('shows the R1 error on the toggle', async () => {
    renderSection({
      initial: { roll_call_enabled: true, auto_confirm: true },
    });
    await validate();
    expect(
      screen.getByText(/Auto-confirm must be off while the ready check/),
    ).toBeVisible();
  });

  it('opens the voice block when one of its fields has an error', async () => {
    renderSection({ initial: { start_cull_enabled: true } });
    expect(screen.queryByTestId(IDS.cullEnabled)).not.toBeInTheDocument();
    await validate();
    expect(
      screen.getByText('The start cull needs an event voice channel.'),
    ).toBeVisible();
  });

  it('opens the settings block on an error even while the check is off', async () => {
    renderSection({
      initial: { ready_check_open_minutes: 20, ready_check_close_minutes: 30 },
    });
    expect(screen.getByTestId(IDS.settingsTrigger)).toBeDisabled();
    await validate();
    expect(
      screen.getByText(/The check must close after it opens/),
    ).toBeVisible();
    expect(screen.getByTestId(IDS.settingsTrigger)).toBeEnabled();
  });

  it('keeps the voice block open once its error is fixed', async () => {
    renderSection({ initial: { voice_presence_confirms: true } });
    await validate();
    click(IDS.voiceConfirms);
    await validate();
    expect(
      screen.queryByText(
        'Voice presence confirms need an event voice channel.',
      ),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId(IDS.voiceConfirms)).toBeInTheDocument();
  });
});
