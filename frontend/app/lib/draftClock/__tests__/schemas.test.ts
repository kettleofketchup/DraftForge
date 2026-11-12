import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { TickEnvelopeSchema } from '~/lib/draftClock';

describe('TickEnvelopeSchema', () => {
  it('accepts the common fields with resuming_until null or absent', () => {
    expect(TickEnvelopeSchema.parse({ draft_state: 'drafting', server_time: '2026-11-08T12:00:00Z' })).toBeTruthy();
    expect(TickEnvelopeSchema.parse({ draft_state: 'resuming', server_time: 'x', resuming_until: null })).toBeTruthy();
  });
  it('rejects a missing server_time', () => {
    expect(TickEnvelopeSchema.safeParse({ draft_state: 'drafting' }).success).toBe(false);
  });
  it('extends with a type literal for a concrete consumer', () => {
    const Hero = TickEnvelopeSchema.extend({ type: z.literal('herodraft_tick') });
    expect(Hero.parse({ type: 'herodraft_tick', draft_state: 'drafting', server_time: 'x' }).type).toBe('herodraft_tick');
  });
});
