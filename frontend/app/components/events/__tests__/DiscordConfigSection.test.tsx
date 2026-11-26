// @vitest-environment jsdom
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { z } from 'zod';

import { Form } from '~/components/ui/form';
import { TestQueryClientProvider } from '~/test/TestQueryClientProvider';
import { DiscordConfigSection } from '../DiscordConfigSection';
import { EVENT_SECTION_FIELDS } from '../form/settingsFields';
import {
  NO_CHANNEL_WARNING,
  SIGNUP_NO_CHANNEL_WARNING,
} from '../postChannelState';
import { DISCORD_CONFIG_DEFAULTS, type discordConfigSchema } from '../schemas';

vi.mock('../DiscordChannelPicker', () => ({
  DiscordChannelPicker: (p: {
    value?: string;
    onChange: (value: string) => void;
    clearable?: { label: string; fallbackChannelId?: string };
    'data-testid'?: string;
  }) => {
    const testId = p['data-testid'] ?? 'channel-picker';
    return (
      <div
        data-testid={testId}
        data-value={p.value ?? ''}
        data-clear-label={p.clearable?.label ?? ''}
        data-fallback={p.clearable?.fallbackChannelId ?? ''}
      >
        {p.clearable && p.value ? (
          <button
            type="button"
            data-testid={`${testId}-clear`}
            onClick={() => p.onChange('')}
          />
        ) : null}
      </div>
    );
  },
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
    <TestQueryClientProvider>
      <Form {...form}>
        <DiscordConfigSection
          control={form.control}
          isRepeater={isRepeater}
          organizationId={7}
          showNotifyNewEvents={showNotifyNewEvents}
        />
      </Form>
    </TestQueryClientProvider>
  );
}

const PICKER = 'discord-announcement-channel-select';
const SERVER_EVENT = 'discord-subsection-server-event';
const CHANNEL_POSTS = 'discord-subsection-channel-posts';
const SIGNUP_PICKER = 'discord-signup-channel-select';
const ATTENDANCE_PICKER = 'discord-confirm-attendance-channel-select';
const PROFILE_PICKER = 'discord-profile-reminder-channel-select';
const NEW_EVENT_PICKER = 'discord-new-event-channel-select';
const BLOCK = 'discord-announcement-channel-block';
const usedBy = () => screen.queryByText(/^Used by:/);
const PRE_DAY = EVENT_SECTION_FIELDS.discord.discord_announcement.label;
const ATTENDANCE =
  EVENT_SECTION_FIELDS.discord.discord_confirm_attendance.label;
const PROFILE = EVENT_SECTION_FIELDS.discord.discord_profile_reminder.label;
const NOTIFY = EVENT_SECTION_FIELDS.discord.discord_notify_new_events.label;
const checkboxLabel = (field: string) =>
  screen.getByTestId(`discord-${field}`).closest('div')?.querySelector('label')
    ?.textContent;

describe('DiscordConfigSection announcement channel', () => {
  it('hides the picker when no setting uses it', () => {
    render(<Harness />);
    expect(screen.queryByTestId(PICKER)).toBeNull();
    expect(screen.queryByTestId(BLOCK)).toBeNull();
  });

  it('shows the picker for the attendance reminder alone', () => {
    render(<Harness initial={{ discord_confirm_attendance: true }} />);
    expect(screen.getByTestId(PICKER)).toBeInTheDocument();
    expect(usedBy()).toHaveTextContent(`Used by: ${ATTENDANCE}`);
    expect(screen.queryByText('Hours before event')).toBeNull();
    expect(screen.queryByText('Mention roles in announcement')).toBeNull();
  });

  it('shows the picker for the profile reminder alone', () => {
    render(<Harness initial={{ discord_profile_reminder: true }} />);
    expect(screen.getByTestId(PICKER)).toBeInTheDocument();
    expect(usedBy()).toHaveTextContent(`Used by: ${PROFILE}`);
  });

  it('shows picker, hours and roles for the pre-day announcement', () => {
    render(<Harness initial={{ discord_announcement: true }} />);
    expect(screen.getByTestId(PICKER)).toBeInTheDocument();
    expect(screen.getByText('Hours before event')).toBeInTheDocument();
    expect(
      screen.getByText('Mention roles in announcement'),
    ).toBeInTheDocument();
    expect(usedBy()).toHaveTextContent(`Used by: ${PRE_DAY}`);
  });

  it('shows the picker for series new-event posts alone', () => {
    render(
      <Harness isRepeater initial={{ discord_notify_new_events: true }} />,
    );
    expect(screen.getByTestId(PICKER)).toBeInTheDocument();
    expect(usedBy()).toHaveTextContent(`Used by: ${NOTIFY}`);
    expect(screen.queryByText(/only when Pre-day announcement/)).toBeNull();
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
    expect(usedBy()).toHaveTextContent(`Used by: ${ATTENDANCE}`);
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
      `Used by: ${[PRE_DAY, ATTENDANCE, PROFILE, NOTIFY].join(', ')}`,
    );
  });

  it('names each user exactly as its checkbox label', () => {
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
    expect(usedBy()?.textContent).toBe(
      `Used by: ${[
        'discord_announcement',
        'discord_confirm_attendance',
        'discord_profile_reminder',
        'discord_notify_new_events',
      ]
        .map(checkboxLabel)
        .join(', ')}`,
    );
  });

  it('links the used-by line to the picker description', () => {
    render(<Harness initial={{ discord_confirm_attendance: true }} />);
    expect(usedBy()?.closest('[id$="-form-item-description"]')).not.toBeNull();
  });

  it('shows the fallback help and places the block last in Channel posts', () => {
    render(
      <Harness isRepeater initial={{ discord_confirm_attendance: true }} />,
    );
    expect(
      screen.getByText(/^Used by posts with no channel of their own\./),
    ).toBeInTheDocument();
    const block = screen.getByTestId(BLOCK);
    expect(block.parentElement).toBe(screen.getByTestId(CHANNEL_POSTS));
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

describe('DiscordConfigSection layout', () => {
  it('renders Server event and Channel posts groups', () => {
    render(<Harness isRepeater />);
    const server = screen.getByTestId(SERVER_EVENT);
    const posts = screen.getByTestId(CHANNEL_POSTS);
    expect(within(server).getByRole('heading', { level: 4 })).toHaveTextContent(
      'Server event',
    );
    expect(within(posts).getByRole('heading', { level: 4 })).toHaveTextContent(
      'Channel posts',
    );
    expect(
      within(server).getByTestId('discord-discord_create_event'),
    ).toBeInTheDocument();
    expect(
      within(posts).queryByTestId('discord-discord_create_event'),
    ).toBeNull();
  });

  it('orders the channel posts', () => {
    render(<Harness isRepeater />);
    const posts = screen.getByTestId(CHANNEL_POSTS);
    const order = [
      'discord_post_signups',
      'discord_start_mention',
      'discord_announcement',
      'discord_confirm_attendance',
      'discord_profile_reminder',
      'discord_notify_new_events',
    ].map((f) => within(posts).getByTestId(`discord-${f}`));
    for (let i = 1; i < order.length; i++) {
      expect(
        order[i - 1].compareDocumentPosition(order[i]) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
  });

  it.each([
    ['discord_post_signups', SIGNUP_PICKER],
    ['discord_confirm_attendance', ATTENDANCE_PICKER],
    ['discord_profile_reminder', PROFILE_PICKER],
    ['discord_notify_new_events', NEW_EVENT_PICKER],
  ])('shows the %s picker only with its toggle on', (toggle, picker) => {
    render(<Harness isRepeater />);
    expect(screen.queryByTestId(picker)).toBeNull();
    fireEvent.click(screen.getByTestId(`discord-${toggle}`));
    expect(
      within(screen.getByTestId(CHANNEL_POSTS)).getByTestId(picker),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTestId(`discord-${toggle}`));
    expect(screen.queryByTestId(picker)).toBeNull();
  });

  it('hides the new-event picker when the toggle is not shown', () => {
    render(
      <Harness
        isRepeater
        showNotifyNewEvents={false}
        initial={{ discord_notify_new_events: true }}
      />,
    );
    expect(screen.queryByTestId(NEW_EVENT_PICKER)).toBeNull();
  });
});

describe('DiscordConfigSection per-post channel pickers', () => {
  const allOn: Partial<Fields> = {
    discord_post_signups: true,
    discord_confirm_attendance: true,
    discord_profile_reminder: true,
    discord_notify_new_events: true,
  };

  it('blank own channel with announcement channel passes the fallback props', () => {
    render(
      <Harness
        isRepeater
        initial={{
          ...allOn,
          discord_announcement: true,
          discord_announcement_channel_id: '222',
        }}
      />,
    );
    for (const id of [
      SIGNUP_PICKER,
      ATTENDANCE_PICKER,
      PROFILE_PICKER,
      NEW_EVENT_PICKER,
    ]) {
      const picker = screen.getByTestId(id);
      expect(picker).toHaveAttribute(
        'data-clear-label',
        'Use announcement channel',
      );
      expect(picker).toHaveAttribute('data-fallback', '222');
      expect(screen.queryByTestId(`${id}-no-channel`)).toBeNull();
    }
  });

  it('falls back to a stored announcement channel with the announcement off', () => {
    render(
      <Harness
        isRepeater
        initial={{ ...allOn, discord_announcement_channel_id: '222' }}
      />,
    );
    for (const id of [ATTENDANCE_PICKER, PROFILE_PICKER, NEW_EVENT_PICKER]) {
      expect(screen.getByTestId(id)).toHaveAttribute('data-fallback', '222');
      expect(screen.queryByTestId(`${id}-no-channel`)).toBeNull();
    }
  });

  it('blank own and announcement channel shows No channel selected and warning', () => {
    render(<Harness isRepeater initial={allOn} />);
    for (const id of [ATTENDANCE_PICKER, PROFILE_PICKER, NEW_EVENT_PICKER]) {
      const picker = screen.getByTestId(id);
      expect(picker).toHaveAttribute('data-clear-label', 'No channel selected');
      expect(picker).toHaveAttribute('data-fallback', '');
      expect(screen.getByTestId(`${id}-no-channel`)).toHaveTextContent(
        NO_CHANNEL_WARNING,
      );
    }
  });

  it('own channel set shows no warning', () => {
    render(
      <Harness
        initial={{
          discord_confirm_attendance: true,
          discord_confirm_attendance_channel_id: '333',
        }}
      />,
    );
    expect(screen.getByTestId(ATTENDANCE_PICKER)).toHaveAttribute(
      'data-value',
      '333',
    );
    expect(screen.queryByTestId(`${ATTENDANCE_PICKER}-no-channel`)).toBeNull();
  });

  it('signup picker warns when announcement toggle is off even with a stored announcement id', () => {
    render(
      <Harness
        initial={{
          discord_post_signups: true,
          discord_announcement: false,
          discord_announcement_channel_id: '222',
        }}
      />,
    );
    const picker = screen.getByTestId(SIGNUP_PICKER);
    expect(picker).toHaveAttribute('data-clear-label', 'No channel selected');
    expect(picker).toHaveAttribute('data-fallback', '');
    expect(screen.getByTestId(`${SIGNUP_PICKER}-no-channel`)).toHaveTextContent(
      SIGNUP_NO_CHANNEL_WARNING,
    );
  });

  it('signup picker is labelled without "(required)"', () => {
    render(<Harness initial={{ discord_post_signups: true }} />);
    expect(screen.getByText('Signup channel')).toBeInTheDocument();
    expect(screen.queryByText(/\(required\)/)).toBeNull();
  });

  it('signup clear button resets to empty', () => {
    render(
      <Harness
        initial={{
          discord_post_signups: true,
          discord_post_signups_channel_id: '444',
        }}
      />,
    );
    fireEvent.click(screen.getByTestId(`${SIGNUP_PICKER}-clear`));
    expect(form.getValues('discord_post_signups_channel_id')).toBe('');
    expect(screen.getByTestId(SIGNUP_PICKER)).toHaveAttribute('data-value', '');
  });

  it('announcement picker sits in the pre-day card when on', () => {
    render(
      <Harness
        initial={{
          discord_announcement: true,
          discord_confirm_attendance: true,
        }}
      />,
    );
    expect(screen.getAllByTestId(PICKER)).toHaveLength(1);
    expect(screen.queryByTestId(BLOCK)).toBeNull();
    const card = screen
      .getByTestId('discord-discord_announcement')
      .closest('div.rounded-md') as HTMLElement;
    expect(within(card).getByTestId(PICKER)).toBeInTheDocument();
  });

  it('fallback block lists only posts with a blank own channel', () => {
    render(
      <Harness
        isRepeater
        initial={{
          ...allOn,
          discord_post_signups_channel_id: '1',
          discord_profile_reminder_channel_id: '2',
        }}
      />,
    );
    expect(screen.getByTestId(BLOCK)).toBeInTheDocument();
    expect(usedBy()?.textContent).toBe(
      `Used by: ${[ATTENDANCE, NOTIFY].join(', ')}`,
    );
  });

  it('fallback block hides when every post has its own channel', () => {
    render(
      <Harness
        isRepeater
        initial={{
          ...allOn,
          discord_confirm_attendance_channel_id: '1',
          discord_profile_reminder_channel_id: '2',
          discord_new_event_channel_id: '3',
        }}
      />,
    );
    expect(screen.queryByTestId(BLOCK)).toBeNull();
    expect(screen.queryByTestId(PICKER)).toBeNull();
  });

  it('hidden picker values are kept', () => {
    render(
      <Harness
        isRepeater
        initial={{
          discord_confirm_attendance: true,
          discord_confirm_attendance_channel_id: '9',
        }}
      />,
    );
    fireEvent.click(screen.getByTestId('discord-discord_confirm_attendance'));
    expect(screen.queryByTestId(ATTENDANCE_PICKER)).toBeNull();
    expect(form.getValues('discord_confirm_attendance_channel_id')).toBe('9');
    fireEvent.click(screen.getByTestId('discord-discord_confirm_attendance'));
    expect(screen.getByTestId(ATTENDANCE_PICKER)).toHaveAttribute(
      'data-value',
      '9',
    );
  });
});
