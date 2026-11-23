import { describe, expect, it } from 'vitest';
import { eventResponseSchema } from '../schemas';

// Zod strips undeclared keys, so a viewer flag missing here silently
// disappears for every caller that parses the event response.
describe('eventResponseSchema viewer flags', () => {
  const viewerFlags = eventResponseSchema.pick({
    user_can_manage: true,
    user_can_manage_event_staff: true,
    user_is_event_operator: true,
  });

  it('keeps user_is_event_operator for helpers and hosts', () => {
    const parsed = viewerFlags.parse({
      user_can_manage: false,
      user_can_manage_event_staff: false,
      user_is_event_operator: true,
    });
    expect(parsed.user_is_event_operator).toBe(true);
  });

  it('defaults user_is_event_operator to false when absent', () => {
    const parsed = viewerFlags.parse({
      user_can_manage: true,
      user_can_manage_event_staff: true,
    });
    expect(parsed.user_is_event_operator).toBe(false);
  });
});
