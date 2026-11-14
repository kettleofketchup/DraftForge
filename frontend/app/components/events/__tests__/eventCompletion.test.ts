import { describe, expect, it } from 'vitest';
import { canCompleteEvent } from '../eventCompletion';
import { EventState, type EventType } from '../schemas';

type Gate = Pick<EventType, 'state' | 'user_can_manage_event_staff'>;

const settled = { settled: true };

describe('canCompleteEvent', () => {
  it.each([
    [EventState.UPCOMING, false],
    [EventState.SIGNUPS_OPEN, false],
    [EventState.ROLL_CALL, true],
    [EventState.IN_PROGRESS, true],
    [EventState.COMPLETED, false],
    [EventState.CANCELLED, false],
  ])('state %s -> %s for event staff managers', (state, expected) => {
    const event = { state, user_can_manage_event_staff: true } as Gate;
    expect(canCompleteEvent(event, settled)).toBe(expected);
  });

  it('is false until feature access has settled', () => {
    const event = { state: EventState.IN_PROGRESS, user_can_manage_event_staff: true } as Gate;
    expect(canCompleteEvent(event, { settled: false })).toBe(false);
  });

  it('is false without the event staff permission', () => {
    const event = { state: EventState.IN_PROGRESS, user_can_manage_event_staff: false } as Gate;
    expect(canCompleteEvent(event, settled)).toBe(false);
  });

  it('is false while the event is loading', () => {
    expect(canCompleteEvent(undefined, settled)).toBe(false);
  });
});
