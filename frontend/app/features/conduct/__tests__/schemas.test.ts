import { describe, expect, it } from 'vitest';
import {
  ConductSettingsFormSchema,
  MemberConductSchema,
  type ConductSettingsForm,
} from '../schemas';
import { historyItem, memberConduct } from './fixtures';

const SETTINGS: ConductSettingsForm = {
  late_cancel_hours: 24,
  late_cancel_weight: 0.5,
  half_life_days: 90,
  max_age_days: 365,
  prior_show_rate: 0.85,
  prior_strength: 3,
  min_events: 3,
  leaderboard_public: true,
  back_of_line_enabled: false,
  back_of_line_below: 0.7,
  require_approval_enabled: false,
  require_approval_below: 0.5,
  block_enabled: false,
  block_below: 0.3,
  enforce_on_new_members: false,
};

describe('MemberConductSchema', () => {
  it('parses a staff payload with reason and set_by', () => {
    const parsed = MemberConductSchema.parse(
      memberConduct({
        history: [
          historyItem({
            outcome: 'no_show',
            source: 'staff',
            reason: 'Did not show',
            set_by: { user_pk: 2, username: 'admin' },
          }),
        ],
      }),
    );
    expect(parsed.history[0].reason).toBe('Did not show');
    expect(parsed.history[0].set_by?.username).toBe('admin');
  });

  it('parses a self payload without reason and set_by', () => {
    const parsed = MemberConductSchema.parse(memberConduct());
    expect(parsed.history[0]).not.toHaveProperty('reason');
    expect(parsed.history[0]).not.toHaveProperty('set_by');
  });

  it('rejects an unknown outcome', () => {
    expect(() =>
      MemberConductSchema.parse({
        ...memberConduct(),
        history: [{ ...historyItem(), outcome: 'teleported' }],
      }),
    ).toThrow();
  });
});

describe('ConductSettingsFormSchema', () => {
  it('accepts the defaults', () => {
    expect(ConductSettingsFormSchema.safeParse(SETTINGS).success).toBe(true);
  });

  it('rejects a half-life below the range', () => {
    const result = ConductSettingsFormSchema.safeParse({
      ...SETTINGS,
      half_life_days: 6,
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].path).toEqual(['half_life_days']);
  });

  it('rejects more than two decimal places', () => {
    const result = ConductSettingsFormSchema.safeParse({
      ...SETTINGS,
      block_below: 0.555,
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].path).toEqual(['block_below']);
  });

  it('rejects a max age below the half-life', () => {
    const result = ConductSettingsFormSchema.safeParse({
      ...SETTINGS,
      half_life_days: 200,
      max_age_days: 100,
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].path).toEqual(['max_age_days']);
  });
});
