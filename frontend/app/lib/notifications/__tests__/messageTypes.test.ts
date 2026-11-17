import { describe, expect, it } from 'vitest';
import {
  MESSAGE_GROUP_KEYS,
  MESSAGE_GROUPS,
  MESSAGE_KEYS,
  MESSAGE_TYPES,
  MessageGroupSchema,
  MessageKeySchema,
  MessageTypeSchema,
} from '~/lib/notifications/messageTypes.generated';

describe('generated message types', () => {
  it('parses every message type and group with its schema', () => {
    for (const type of MESSAGE_TYPES) {
      expect(MessageTypeSchema.parse(type)).toEqual(type);
    }
    for (const group of MESSAGE_GROUPS) {
      expect(MessageGroupSchema.parse(group)).toEqual(group);
    }
  });

  it('accepts known keys and rejects unknown ones', () => {
    expect(MessageKeySchema.parse('rsvp.promotion')).toBe('rsvp.promotion');
    expect(MessageKeySchema.safeParse('rsvp.nope').success).toBe(false);
  });

  it('keeps the key arrays in step with the catalogue', () => {
    expect(MESSAGE_TYPES.map((t) => t.key)).toEqual([...MESSAGE_KEYS]);
    expect(MESSAGE_GROUPS.map((g) => g.key)).toEqual([...MESSAGE_GROUP_KEYS]);
  });

  it('marks the promotion message essential and urgent', () => {
    const promotion = MESSAGE_TYPES.find((t) => t.key === 'rsvp.promotion');
    expect(promotion).toMatchObject({
      group: 'roster_changes',
      essentialDefault: true,
      urgent: true,
    });
  });
});
