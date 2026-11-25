// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { z } from 'zod';
import { Form } from '~/components/ui/form';
import type { DiscordPreviewContext } from '~/features/event-discord-preview';
import { previewResponse } from '~/features/event-discord-preview/__tests__/fixtures';
import { TestQueryClientProvider } from '~/test/TestQueryClientProvider';
import { DiscordConfigSection } from '../DiscordConfigSection';
import { DISCORD_CONFIG_DEFAULTS, type discordConfigSchema } from '../schemas';

const mocks = vi.hoisted(() => ({ preview: vi.fn() }));

vi.mock('~/features/event-discord-preview/api', () => ({
  previewEventDiscordMessage: mocks.preview,
}));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
}));
vi.mock('../DiscordChannelPicker', () => ({
  DiscordChannelPicker: () => <div data-testid="channel-picker" />,
}));
vi.mock('../DiscordRolePicker', () => ({
  DiscordRolePicker: () => <div data-testid="role-picker" />,
}));

type Fields = z.input<typeof discordConfigSchema> & {
  discord_notify_new_events?: boolean;
};

beforeEach(() => mocks.preview.mockReset());

function Harness({
  isRepeater,
  showNotifyNewEvents,
  previewContext,
  initial = {},
}: {
  isRepeater: boolean;
  showNotifyNewEvents?: boolean;
  previewContext?: DiscordPreviewContext;
  initial?: Partial<Fields>;
}) {
  const form = useForm<Fields>({
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
          showNotifyNewEvents={showNotifyNewEvents}
          organizationId={7}
          previewContext={previewContext}
        />
      </Form>
    </TestQueryClientProvider>
  );
}

const previewIds = () =>
  screen
    .queryAllByTestId(/^discord-preview-/)
    .map((el) => el.getAttribute('data-testid'))
    .sort();

describe('DiscordConfigSection preview buttons', () => {
  it('puts a preview button on every message-sending block of a series', () => {
    render(
      <Harness
        isRepeater
        initial={{ discord_create_event: true }}
        previewContext={{ type: 'repeater', repeaterId: 3 }}
      />,
    );
    expect(previewIds()).toEqual(
      [
        'discord-preview-announcement_notice',
        'discord-preview-attendance_reminder',
        'discord-preview-new_event_post',
        'discord-preview-profile_reminder',
        'discord-preview-scheduled_event',
        'discord-preview-scheduled_event_sync',
        'discord-preview-signup_post',
        'discord-preview-signup_reminder',
        'discord-preview-start_mention',
      ].sort(),
    );
  });

  it('hides the series-only previews for a single event', () => {
    render(
      <Harness
        isRepeater={false}
        previewContext={{ type: 'event', eventId: 42 }}
      />,
    );
    const ids = previewIds();
    expect(ids).not.toContain('discord-preview-signup_reminder');
    expect(ids).not.toContain('discord-preview-new_event_post');
    expect(ids).not.toContain('discord-preview-scheduled_event_sync');
    expect(ids).toContain('discord-preview-signup_post');
  });

  it('gives mark-interested and the channel picker no preview', () => {
    render(
      <Harness
        isRepeater={false}
        initial={{
          discord_create_event: true,
          discord_announcement: true,
        }}
        previewContext={{ type: 'event', eventId: 42 }}
      />,
    );
    const interested = screen
      .getByTestId('discord-discord_mark_interested')
      .closest('div');
    expect(
      interested?.querySelector('[data-testid^="discord-preview-"]'),
    ).toBeNull();
    const block = screen.getByTestId('discord-announcement-channel-block');
    expect(block.querySelector('[data-testid^="discord-preview-"]')).toBeNull();
  });

  it('shows a static note for org defaults and makes no request', async () => {
    render(<Harness isRepeater={false} />);
    fireEvent.click(screen.getByTestId('discord-preview-signup_post'));
    expect(
      await screen.findByTestId('discord-preview-unavailable'),
    ).toBeInTheDocument();
    expect(mocks.preview).not.toHaveBeenCalled();
  });

  it('does not submit the surrounding form', async () => {
    const onSubmit = vi.fn();
    render(
      <form onSubmit={onSubmit}>
        <Harness
          isRepeater={false}
          previewContext={{ type: 'event', eventId: 42 }}
        />
      </form>,
    );
    mocks.preview.mockResolvedValue(
      previewResponse({ kind: 'profile_reminder' }),
    );
    fireEvent.click(screen.getByTestId('discord-preview-profile_reminder'));
    expect(
      await screen.findByTestId('discord-preview-dialog'),
    ).toBeInTheDocument();
    expect(
      await screen.findByTestId('discord-message-preview'),
    ).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
