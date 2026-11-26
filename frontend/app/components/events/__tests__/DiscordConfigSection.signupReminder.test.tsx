// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import { Form } from '~/components/ui/form';
import {
  DiscordConfigSection,
  type DiscordFields,
} from '../DiscordConfigSection';
import {
  EVENT_SECTION_FIELDS,
  SIGNUP_REMINDER_LABEL,
} from '../form/settingsFields';
import { Wrapper } from './eventModalFixtures';

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
}));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

const SUBSCRIBE_NOTE =
  "Members subscribe on the series page, or with Notify Me on the event's signup post in Discord.";

function Harness({
  isRepeater,
  showSignupReminder,
  signupReminder = true,
  notifyNewEvents = false,
}: {
  isRepeater: boolean;
  showSignupReminder?: boolean;
  signupReminder?: boolean;
  notifyNewEvents?: boolean;
}) {
  const form = useForm<DiscordFields>({
    defaultValues: {
      discord_signup_reminder: signupReminder,
      discord_signup_reminder_hours: 24,
      discord_notify_new_events: notifyNewEvents,
    },
  });
  return (
    <Wrapper>
      <Form {...form}>
        <DiscordConfigSection
          control={form.control}
          isRepeater={isRepeater}
          organizationId={1}
          showSignupReminder={showSignupReminder}
        />
      </Form>
    </Wrapper>
  );
}

const meta = EVENT_SECTION_FIELDS.discord.discord_signup_reminder;
const dmGroup = () => screen.getByTestId('discord-subsection-direct-messages');

describe('DiscordConfigSection direct messages', () => {
  it('direct messages group holds the signup reminder for series', () => {
    render(<Harness isRepeater />);
    const group = dmGroup();
    expect(
      within(group).getByRole('heading', { name: 'Direct messages' }),
    ).toBeInTheDocument();
    expect(
      within(group).getByTestId('discord-discord_signup_reminder'),
    ).toBeInTheDocument();
    expect(
      within(group).getByTestId('discord-discord_signup_reminder_hours-select'),
    ).toBeInTheDocument();
    expect(within(group).getByText(SIGNUP_REMINDER_LABEL)).toBeInTheDocument();
    expect(within(group).getByText(meta.description!)).toBeInTheDocument();
    expect(
      within(
        screen.getByTestId('discord-subsection-channel-posts'),
      ).queryByTestId('discord-discord_signup_reminder'),
    ).toBeNull();
    expect(
      screen.queryByTestId('discord-direct-messages-series-only'),
    ).toBeNull();
  });

  it('places Direct messages after Channel posts', () => {
    render(<Harness isRepeater />);
    const posts = screen.getByTestId('discord-subsection-channel-posts');
    expect(
      posts.compareDocumentPosition(dmGroup()) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('single events show the series-only line', () => {
    render(<Harness isRepeater={false} />);
    const line = within(dmGroup()).getByTestId(
      'discord-direct-messages-series-only',
    );
    expect(line).toHaveTextContent(
      'Direct messages are set on recurring series.',
    );
    expect(screen.queryByTestId('discord-discord_signup_reminder')).toBeNull();
    expect(
      screen.queryByTestId('discord-signup-reminder-subscribe-note'),
    ).toBeNull();
  });

  it('org defaults show the default-for-new-series toggle without the series-only line', () => {
    render(<Harness isRepeater={false} showSignupReminder />);
    const group = dmGroup();
    expect(
      within(group).getByTestId('discord-discord_signup_reminder'),
    ).toBeInTheDocument();
    expect(
      within(group).getByText('Signup reminder DM (default for new series)'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('discord-direct-messages-series-only'),
    ).toBeNull();
  });

  it.each([true, false])(
    'subscribe note names the series page and Notify Me (notify new events %s)',
    (notifyNewEvents) => {
      render(<Harness isRepeater notifyNewEvents={notifyNewEvents} />);
      const note = within(dmGroup()).getByTestId(
        'discord-signup-reminder-subscribe-note',
      );
      expect(note).toHaveTextContent(SUBSCRIBE_NOTE);
      expect(note).toHaveClass('text-muted-foreground');
      expect(note.closest('[role="alert"]')).toBeNull();
      expect(within(dmGroup()).queryByRole('alert')).toBeNull();
    },
  );

  it('shows the subscribe note while the reminder is off', () => {
    render(<Harness isRepeater signupReminder={false} />);
    expect(
      screen.getByTestId('discord-signup-reminder-subscribe-note'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('discord-discord_signup_reminder_hours-select'),
    ).toBeNull();
  });
});
