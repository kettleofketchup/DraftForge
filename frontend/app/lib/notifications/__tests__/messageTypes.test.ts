import { describe, expect, it } from 'vitest';
import {
  GroupKeySchema,
  MESSAGE_REGISTRY,
  MessageKeySchema,
  MessageRegistrySchema,
  MessageTypeSchema,
} from '~/lib/notifications/messageTypes.generated';

const { groups, messageTypes } = MESSAGE_REGISTRY;

describe('generated message types', () => {
  it('parses the whole registry with its schema', () => {
    expect(MessageRegistrySchema.parse(MESSAGE_REGISTRY)).toEqual(
      MESSAGE_REGISTRY,
    );
  });

  it('accepts known keys and rejects unknown ones', () => {
    expect(MessageKeySchema.parse('rsvp.promotion')).toBe('rsvp.promotion');
    expect(MessageKeySchema.safeParse('rsvp.nope').success).toBe(false);
  });

  it('carries the pydantic field constraints', () => {
    const valid = messageTypes[0];
    for (const bad of [
      { ...valid, label: ' ' },
      { ...valid, channels: [] },
      { ...valid, extra: true },
    ]) {
      expect(MessageTypeSchema.safeParse(bad).success).toBe(false);
    }
  });

  it('keeps the key enums in step with the catalogue', () => {
    expect(messageTypes.map((t) => t.key)).toEqual(MessageKeySchema.options);
    expect(groups.map((g) => g.key)).toEqual(GroupKeySchema.options);
  });

  it('marks the promotion message essential and urgent', () => {
    const promotion = messageTypes.find((t) => t.key === 'rsvp.promotion');
    expect(promotion).toMatchObject({
      group: 'roster_changes',
      essentialDefault: true,
      urgent: true,
    });
  });
});
