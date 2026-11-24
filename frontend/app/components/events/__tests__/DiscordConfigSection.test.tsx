// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { z } from 'zod';

import { Form } from '~/components/ui/form';
import { DiscordConfigSection } from '../DiscordConfigSection';
import { DISCORD_CONFIG_DEFAULTS, type discordConfigSchema } from '../schemas';

vi.mock('../DiscordChannelPicker', () => ({
  DiscordChannelPicker: (p: { value?: string; 'data-testid'?: string }) => (
    <div
      data-testid={p['data-testid'] ?? 'channel-picker'}
      data-value={p.value ?? ''}
    />
  ),
}));
vi.mock('../DiscordRolePicker', () => ({
  DiscordRolePicker: () => <div data-testid="role-picker" />,
}));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

type Fields = z.input<typeof discordConfigSchema> & {
  discord_notify_new_events?: boolean;
};

let form: UseFormReturn<Fields>;

function Harness({
  initial,
  isRepeater = false,
  showNotifyNewEvents,
}: {
  initial?: Partial<Fields>;
  isRepeater?: boolean;
  showNotifyNewEvents?: boolean;
}) {
  form = useForm<Fields>({
    defaultValues: {
      ...DISCORD_CONFIG_DEFAULTS,
      discord_notify_new_events: false,
      ...initial,
    },
  });
  return (
    <Form {...form}>
      <DiscordConfigSection
        control={form.control}
        isRepeater={isRepeater}
        organizationId={7}
        showNotifyNewEvents={showNotifyNewEvents}
      />
    </Form>
  );
}

const PICKER = 'discord-announcement-channel-select';
const BLOCK = 'discord-announcement-channel-block';
const NOTIFY_NOTE =
  'Message interested users posts new events here only when Pre-day announcement is also on.';
const usedBy = () => screen.queryByText(/^Used by:/);

describe('DiscordConfigSection announcement channel', () => {
  it('hides the picker when no setting uses it', () => {
    render(<Harness />);
    expect(screen.queryByTestId(PICKER)).toBeNull();
    expect(screen.queryByTestId(BLOCK)).toBeNull();
  });

  it('shows the picker for the attendance reminder alone', () => {
    render(<Harness initial={{ discord_confirm_attendance: true }} />);
    expect(screen.getByTestId(PICKER)).toBeInTheDocument();
    expect(usedBy()).toHaveTextContent(/^Used by: Attendance reminder$/);
    expect(screen.queryByText('Hours before event')).toBeNull();
    expect(screen.queryByText('Mention roles in announcement')).toBeNull();
  });

  it('shows the picker for the profile reminder alone', () => {
    render(<Harness initial={{ discord_profile_reminder: true }} />);
    expect(screen.getByTestId(PICKER)).toBeInTheDocument();
    expect(usedBy()).toHaveTextContent(/^Used by: Profile reminder$/);
  });

  it('shows picker, hours and roles for the pre-day announcement', () => {
    render(<Harness initial={{ discord_announcement: true }} />);
    expect(screen.getByTestId(PICKER)).toBeInTheDocument();
    expect(screen.getByText('Hours before event')).toBeInTheDocument();
    expect(
      screen.getByText('Mention roles in announcement'),
    ).toBeInTheDocument();
    expect(usedBy()).toHaveTextContent(/^Used by: Pre-day announcement$/);
  });

  it('shows the picker and the gate note for series new-event posts', () => {
    render(
      <Harness isRepeater initial={{ discord_notify_new_events: true }} />,
    );
    expect(screen.getByTestId(PICKER)).toBeInTheDocument();
    expect(usedBy()).toHaveTextContent(
      /^Used by: Message interested users \(new-event posts\)$/,
    );
    expect(screen.getByText(NOTIFY_NOTE)).toBeInTheDocument();
  });

  it('drops the notify note when pre-day is on', () => {
    render(
      <Harness
        isRepeater
        initial={{
          discord_notify_new_events: true,
          discord_announcement: true,
        }}
      />,
    );
    expect(
      screen.queryByText(/only when Pre-day announcement is also on/),
    ).toBeNull();
  });

  it('hides the picker when notify is on but not shown', () => {
    render(
      <Harness
        isRepeater
        showNotifyNewEvents={false}
        initial={{ discord_notify_new_events: true }}
      />,
    );
    expect(screen.queryByTestId(PICKER)).toBeNull();
  });

  it('ignores hidden notify on a single event (default prop)', () => {
    render(<Harness initial={{ discord_notify_new_events: true }} />);
    expect(screen.queryByTestId(PICKER)).toBeNull();
    expect(
      screen.queryByText(/only when Pre-day announcement is also on/),
    ).toBeNull();
  });

  it('shows only attendance when notify is hidden on a single event', () => {
    render(
      <Harness
        initial={{
          discord_notify_new_events: true,
          discord_confirm_attendance: true,
        }}
      />,
    );
    expect(screen.getByTestId(PICKER)).toBeInTheDocument();
    expect(usedBy()).toHaveTextContent(/^Used by: Attendance reminder$/);
    expect(
      screen.queryByText(/only when Pre-day announcement is also on/),
    ).toBeNull();
  });

  it('lists every enabled user once and renders one picker', () => {
    render(
      <Harness
        isRepeater
        initial={{
          discord_announcement: true,
          discord_confirm_attendance: true,
          discord_profile_reminder: true,
          discord_notify_new_events: true,
        }}
      />,
    );
    expect(screen.getAllByTestId(PICKER)).toHaveLength(1);
    expect(usedBy()).toHaveTextContent(
      /^Used by: Pre-day announcement, Attendance reminder, Profile reminder, Message interested users \(new-event posts\)$/,
    );
  });

  it('shows the shared help and places the block last', () => {
    render(
      <Harness isRepeater initial={{ discord_confirm_attendance: true }} />,
    );
    expect(
      screen.getByText(
        'Shared by the pre-day announcement, attendance reminder, profile reminder and series new-event posts ("Message interested users").',
      ),
    ).toBeInTheDocument();
    const block = screen.getByTestId(BLOCK);
    expect(block.parentElement?.lastElementChild).toBe(block);
  });

  it('toggles with the attendance checkbox', () => {
    render(<Harness />);
    fireEvent.click(screen.getByTestId('discord-discord_confirm_attendance'));
    expect(screen.getByTestId(PICKER)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('discord-discord_confirm_attendance'));
    expect(screen.queryByTestId(PICKER)).toBeNull();
  });

  it('keeps the channel value while the block is hidden', () => {
    render(<Harness initial={{ discord_confirm_attendance: true }} />);
    act(() => form.setValue('discord_announcement_channel_id', 'chan-1'));
    fireEvent.click(screen.getByTestId('discord-discord_confirm_attendance'));
    expect(form.getValues('discord_announcement_channel_id')).toBe('chan-1');
    fireEvent.click(screen.getByTestId('discord-discord_profile_reminder'));
    expect(screen.getByTestId(PICKER)).toHaveAttribute('data-value', 'chan-1');
  });
});
