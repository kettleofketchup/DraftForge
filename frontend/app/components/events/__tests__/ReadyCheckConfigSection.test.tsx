// @vitest-environment jsdom
import { zodResolver } from '@hookform/resolvers/zod';
import { fireEvent, render, screen } from '@testing-library/react';
import { useForm, type Resolver, type UseFormReturn } from 'react-hook-form';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import { Form } from '~/components/ui/form';
import { ReadyCheckConfigSection } from '../ReadyCheckConfigSection';
import { READY_CHECK_TEST_IDS as IDS } from '../form/testIds';
import {
  READY_CHECK_CONFIG_DEFAULTS,
  readyCheckConfigSchema,
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
    resolver: zodResolver(readyCheckConfigSchema) as Resolver<ReadyCheckFields>,
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

describe('ReadyCheckConfigSection', () => {
  it('toggle on applies the automatic preset', () => {
    renderSection({ initial: { auto_confirm: true } });
    click(IDS.toggle);
    expect(form.getValues('roll_call_enabled')).toBe(true);
    expect(form.getValues('roll_call_mode')).toBe('automatic');
    expect(form.getValues('auto_confirm')).toBe(false);
    expect(form.formState.dirtyFields.roll_call_enabled).toBe(true);
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
});
