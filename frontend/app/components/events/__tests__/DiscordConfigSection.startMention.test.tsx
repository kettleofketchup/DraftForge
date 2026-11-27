// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { z } from 'zod';

import { Form } from '~/components/ui/form';
import { TestQueryClientProvider } from '~/test/TestQueryClientProvider';
import { DiscordConfigSection } from '../DiscordConfigSection';
import { DISCORD_CONFIG_DEFAULTS, type discordConfigSchema } from '../schemas';
import {
  START_MENTION_PREREQUISITE_NOTE,
  startMentionPrerequisiteMessage,
} from '../startMentionPrerequisite';

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
  DiscordRolePicker: (props: { 'data-testid'?: string }) => (
    <div data-testid={props['data-testid']} />
  ),
}));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

type Fields = z.input<typeof discordConfigSchema>;

let form: UseFormReturn<Fields>;

function Harness({ initial }: { initial: Partial<Fields> }) {
  form = useForm<Fields>({
    defaultValues: { ...DISCORD_CONFIG_DEFAULTS, ...initial },
  });
  return (
    <TestQueryClientProvider>
      <Form {...form}>
        <DiscordConfigSection
          control={form.control}
          isRepeater={false}
          organizationId={1}
        />
      </Form>
    </TestQueryClientProvider>
  );
}

function renderSection(initial: Partial<Fields> = {}) {
  render(<Harness initial={initial} />);
}

const warning = () =>
  screen.queryByTestId('discord-start-mention-prerequisite-warning');
const fallback = () =>
  screen.queryByTestId('discord-start-mention-prerequisite-fallback');
const note = () =>
  screen.queryByTestId('discord-start-mention-prerequisite-note');

describe('DiscordConfigSection start mention prerequisite', () => {
  it('shows nothing when start mention is off', () => {
    renderSection({ discord_start_mention: false });
    expect(warning()).toBeNull();
    expect(fallback()).toBeNull();
    expect(note()).toBeNull();
  });

  it('warns when signup posts are off', () => {
    renderSection({ discord_start_mention: true });
    expect(warning()).toHaveTextContent(
      startMentionPrerequisiteMessage({
        kind: 'missing',
        reason: 'signup_disabled',
        announcementOn: false,
      })!,
    );
    expect(warning()?.textContent).toContain(
      'or turn on the pre-day announcement with a channel.',
    );
    expect(note()).toHaveTextContent(START_MENTION_PREREQUISITE_NOTE);
    expect(fallback()).toBeNull();
  });

  it('warns when signup posts are off even with a stored signup channel', () => {
    renderSection({
      discord_start_mention: true,
      discord_post_signups: false,
      discord_post_signups_channel_id: '1',
    });
    expect(warning()).toHaveTextContent(
      startMentionPrerequisiteMessage({
        kind: 'missing',
        reason: 'signup_disabled',
        announcementOn: false,
      })!,
    );
  });

  it('warns when no signup channel is selected', () => {
    renderSection({
      discord_start_mention: true,
      discord_post_signups: true,
      discord_post_signups_channel_id: '',
    });
    expect(warning()).toHaveTextContent(
      startMentionPrerequisiteMessage({
        kind: 'missing',
        reason: 'signup_no_channel',
        announcementOn: false,
      })!,
    );
  });

  it('suggests picking an announcement channel when the announcement has none', () => {
    renderSection({
      discord_start_mention: true,
      discord_post_signups: false,
      discord_announcement: true,
      discord_announcement_channel_id: '',
    });
    expect(warning()?.textContent).toMatch(
      /or pick an announcement channel\.$/,
    );
    expect(fallback()).toBeNull();
  });

  it('shows the fallback note for announcement-only events', () => {
    renderSection({
      discord_start_mention: true,
      discord_post_signups: false,
      discord_announcement: true,
      discord_announcement_channel_id: '2',
    });
    expect(warning()).toBeNull();
    expect(fallback()).toHaveTextContent(
      startMentionPrerequisiteMessage({
        kind: 'announcement_fallback',
        reason: 'signup_disabled',
      })!,
    );
    expect(note()).not.toBeNull();
  });

  it('warning disappears once a signup channel is set', () => {
    renderSection({
      discord_start_mention: true,
      discord_post_signups: true,
      discord_post_signups_channel_id: '',
    });
    expect(warning()).not.toBeNull();
    act(() => {
      form.setValue('discord_post_signups_channel_id', '1');
    });
    expect(warning()).toBeNull();
    expect(note()).not.toBeNull();
  });

  it('ok config shows only the static note', () => {
    renderSection({
      discord_start_mention: true,
      discord_post_signups: true,
      discord_post_signups_channel_id: '1',
    });
    expect(note()).toHaveTextContent(START_MENTION_PREREQUISITE_NOTE);
    expect(warning()).toBeNull();
    expect(fallback()).toBeNull();
  });
});
