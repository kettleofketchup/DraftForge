import { describe, expect, it } from 'vitest';
import { EVENT_TAB_META, eventTabForField, READY_CHECK_FIELDS } from '../tabs';

describe('eventTabForField', () => {
  it.each([
    ['event_voice_channel_id', 'ready'],
    ['ready_check_close_minutes', 'ready'],
    ['roll_call_enabled', 'ready'],
    ['auto_confirm', 'ready'],
    ['start_cull_enabled', 'ready'],
    ['discord_event_title', 'discord'],
    ['min_mmr', 'approval'],
    ['name', 'event'],
  ])('%s -> %s', (field, tab) => {
    expect(eventTabForField(field)).toBe(tab);
  });

  it('labels the ready tab', () => {
    expect(EVENT_TAB_META.ready.label).toBe('Ready check');
    expect(EVENT_TAB_META.ready.icon).toBeDefined();
  });

  it('holds the 17 ready check keys', () => {
    expect(READY_CHECK_FIELDS.size).toBe(17);
  });
});
