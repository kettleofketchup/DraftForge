import { expect, it } from 'vitest';
import { DraftOptionsFormSchema, draftOptionsFormToPatch, draftOptionsToFormInput } from '~/components/teamdraft/schemas';

const ok = (grace: unknown, reserve: unknown) => DraftOptionsFormSchema.safeParse({ timer_enabled: true, grace_time_s: grace, reserve_time_s: reserve });

it('accepts whole seconds (number or digit string) and converts to ms', () => {
  const v = DraftOptionsFormSchema.parse({ timer_enabled: true, grace_time_s: '20', reserve_time_s: '0' });
  expect(draftOptionsFormToPatch(v)).toEqual({ timer_enabled: true, grace_time_ms: 20000, reserve_time_ms: 0 });
});

it('rejects fractional, empty, null and out-of-range values', () => {
  expect(ok('0.5', 5).success).toBe(false);
  expect(ok('', 5).success).toBe(false);
  expect(ok(0, 5).success).toBe(false);
  expect(ok(5, -1).success).toBe(false);
  expect(ok(5, '').success).toBe(false);
  expect(ok(5, null).success).toBe(false);
});

it('draftOptionsToFormInput converts ms to seconds and defaults to 30/30 when options are absent', () => {
  expect(draftOptionsToFormInput({ timer_enabled: false, grace_time_ms: 20000, reserve_time_ms: 0, timeout_action: 'skip_turn' })).toEqual({ timer_enabled: false, grace_time_s: 20, reserve_time_s: 0 });
  expect(draftOptionsToFormInput(undefined)).toEqual({ timer_enabled: true, grace_time_s: 30, reserve_time_s: 30 });
});
