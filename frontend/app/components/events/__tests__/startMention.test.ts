import { describe, expect, it } from 'vitest';
import {
  DISCORD_CONFIG_DEFAULTS,
  discordConfigSchema,
} from '~/components/events/schemas';
import {
  fireConfirmDescription,
  type TaskEntry,
} from '~/components/events/TaskScheduleSection';

const startMentionFields = discordConfigSchema.pick({
  discord_start_mention: true,
  discord_start_mention_minutes: true,
  discord_start_mention_scope: true,
});

const task = (overrides: Partial<TaskEntry> = {}): TaskEntry => ({
  task: 'start_mention',
  label: 'Start Mention',
  fires_at: null,
  status: 'pending',
  description: '',
  check_interval: 'Every 30s',
  last_fired_at: null,
  fired_by: null,
  can_fire: true,
  ...overrides,
});

describe('start mention settings', () => {
  it('defaults to off, 15 minutes, all active signups', () => {
    expect(startMentionFields.parse({})).toEqual({
      discord_start_mention: false,
      discord_start_mention_minutes: 15,
      discord_start_mention_scope: 'all_active',
    });
    expect(DISCORD_CONFIG_DEFAULTS.discord_start_mention_minutes).toBe(15);
    expect(DISCORD_CONFIG_DEFAULTS.discord_start_mention_scope).toBe(
      'all_active',
    );
  });

  it('rejects a lead time under one minute and unknown scopes', () => {
    expect(
      startMentionFields.safeParse({ discord_start_mention_minutes: 0 })
        .success,
    ).toBe(false);
    expect(
      startMentionFields.safeParse({ discord_start_mention_scope: 'everyone' })
        .success,
    ).toBe(false);
    expect(
      startMentionFields.safeParse({ discord_start_mention_scope: 'main' })
        .success,
    ).toBe(true);
  });
});

describe('fireConfirmDescription', () => {
  it('warns that firing start mention pings every member once', () => {
    expect(fireConfirmDescription(task())).toMatch(/@mention every signed-up/);
  });

  it('keeps the generic text for other tasks', () => {
    expect(
      fireConfirmDescription(
        task({ task: 'profile_reminder', label: 'Profile Reminder' }),
      ),
    ).toContain('"Profile Reminder"');
  });
});
