import { z } from 'zod';
import { TickEnvelopeSchema } from '~/lib/draftClock';
import { TeamSchema } from '../team/schemas';
import { UserSchema } from '../user/schemas';

export const TeamDraftStateSchema = z.enum([
  'pending',
  'drafting',
  'paused',
  'resuming',
  'completed',
]);
export type TeamDraftState = z.infer<typeof TeamDraftStateSchema>;

export const DraftOptionsSchema = z.object({
  timer_enabled: z.boolean(),
  grace_time_ms: z.number().int(),
  reserve_time_ms: z.number().int(),
  timeout_action: z.string(),
  hero_timer_enabled: z.boolean().optional(),
  hero_grace_time_ms: z.number().int().optional(),
  hero_reserve_time_ms: z.number().int().optional(),
});
export type DraftOptions = z.infer<typeof DraftOptionsSchema>;

export const DraftTickSchema = TickEnvelopeSchema.extend({
  type: z.literal('draft_tick'),
  active_round_pk: z.number().nullable(),
  active_pick_number: z.number().nullable(),
  active_captain_id: z.number().nullable(),
  active_team_id: z.number().nullable(),
  round_started_at: z.string().nullable(),
  round_timed_out_at: z.string().nullable(),
  round_grace_time_ms: z.number().nullable(),
  teams: z.array(
    z.object({
      team_id: z.number(),
      captain_id: z.number().nullable(),
      reserve_ms: z.number().nullable(),
      is_connected: z.boolean(),
      is_ready: z.boolean(),
    }),
  ),
});
export type DraftTick = z.infer<typeof DraftTickSchema>;

// No z.coerce: Number('') === 0 would silently save reserve 0 ms.
const wholeSeconds = (min: number) =>
  z.preprocess(
    (v) => (typeof v === 'string' ? v.trim() : v),
    z
      .union([z.number(), z.string().regex(/^\d+$/, 'Whole seconds only')])
      .transform(Number)
      .pipe(
        z
          .number()
          .int('Whole seconds only')
          .min(
            min,
            min === 0 ? 'Cannot be negative' : `At least ${min} second`,
          ),
      ),
  );

export const DraftOptionsFormSchema = z.object({
  timer_enabled: z.boolean(),
  grace_time_s: wholeSeconds(1),
  reserve_time_s: wholeSeconds(0),
});
export type DraftOptionsFormInput = z.input<typeof DraftOptionsFormSchema>;
export type DraftOptionsFormValues = z.output<typeof DraftOptionsFormSchema>;
export type DraftOptionsPatch = {
  timer_enabled: boolean;
  grace_time_ms: number;
  reserve_time_ms: number;
};

export function draftOptionsFormToPatch(
  v: DraftOptionsFormValues,
): DraftOptionsPatch {
  return {
    timer_enabled: v.timer_enabled,
    grace_time_ms: v.grace_time_s * 1000,
    reserve_time_ms: v.reserve_time_s * 1000,
  };
}

export function draftOptionsToFormInput(
  o: DraftOptions | null | undefined,
): DraftOptionsFormInput {
  if (!o) return { timer_enabled: true, grace_time_s: 30, reserve_time_s: 30 };
  return {
    timer_enabled: o.timer_enabled,
    grace_time_s: o.grace_time_ms / 1000,
    reserve_time_s: o.reserve_time_ms / 1000,
  };
}

export const DRAFT_STYLE_VALUES = ['shuffle', 'snake', 'normal'] as const;
export type DraftStyleValue = (typeof DRAFT_STYLE_VALUES)[number];
export const DRAFT_STYLE_LABELS: Record<DraftStyleValue, string> = {
  shuffle: 'Shuffle — MMR point buy draft',
  snake: 'Snake Draft — Captains pick in snake order',
  normal: 'Manual — Manually assign players',
};

export const TIMEOUT_ACTION_VALUES = ['skip_turn'] as const;
export type TimeoutActionValue = (typeof TIMEOUT_ACTION_VALUES)[number];
export const TIMEOUT_ACTION_LABELS: Record<TimeoutActionValue, string> = {
  skip_turn: 'Skip turn',
};

export function toTimeoutAction(
  v: string | null | undefined,
): TimeoutActionValue {
  return (TIMEOUT_ACTION_VALUES as readonly string[]).includes(v ?? '')
    ? (v as TimeoutActionValue)
    : 'skip_turn';
}

export function toDraftStyle(v: string | null | undefined): DraftStyleValue {
  return (DRAFT_STYLE_VALUES as readonly string[]).includes(v ?? '')
    ? (v as DraftStyleValue)
    : 'shuffle';
}

export const DRAFT_SETTINGS_DEFAULTS_MS = {
  timer_enabled: true,
  grace_time_ms: 30000,
  reserve_time_ms: 30000,
  timeout_action: 'skip_turn' as TimeoutActionValue,
  hero_timer_enabled: true,
  hero_grace_time_ms: 30000,
  hero_reserve_time_ms: 90000,
};

export const DRAFT_SETTINGS_SECONDS_MIN = {
  draft_grace_time_s: 1,
  draft_reserve_time_s: 0,
  hero_grace_time_s: 1,
  hero_reserve_time_s: 0,
} as const;

/** Seconds-based form fields shared by the tournament and event dialogs. */
const D = DRAFT_SETTINGS_DEFAULTS_MS;
const M = DRAFT_SETTINGS_SECONDS_MIN;
export const DraftSettingsFormSchema = z.object({
  draft_timer_enabled: z.boolean().default(D.timer_enabled),
  draft_grace_time_s: wholeSeconds(M.draft_grace_time_s).default(
    D.grace_time_ms / 1000,
  ),
  draft_reserve_time_s: wholeSeconds(M.draft_reserve_time_s).default(
    D.reserve_time_ms / 1000,
  ),
  draft_timeout_action: z.enum(TIMEOUT_ACTION_VALUES).default(D.timeout_action),
  hero_timer_enabled: z.boolean().default(D.hero_timer_enabled),
  hero_grace_time_s: wholeSeconds(M.hero_grace_time_s).default(
    D.hero_grace_time_ms / 1000,
  ),
  hero_reserve_time_s: wholeSeconds(M.hero_reserve_time_s).default(
    D.hero_reserve_time_ms / 1000,
  ),
});
export type DraftSettingsFormInput = z.input<typeof DraftSettingsFormSchema>;
export type DraftSettingsFormValues = z.output<typeof DraftSettingsFormSchema>;

export function isValidSeconds(v: unknown, min: number): boolean {
  return wholeSeconds(min).safeParse(v).success;
}

/** Nested ``draft_options`` as written by the tournament API (timeout_action is read-only there). */
export type DraftSettingsPatch = {
  timer_enabled: boolean;
  grace_time_ms: number;
  reserve_time_ms: number;
  hero_timer_enabled: boolean;
  hero_grace_time_ms: number;
  hero_reserve_time_ms: number;
};

/** Flat fields as written by the event / repeater API. */
export type EventDraftSettingsFields = {
  draft_timer_enabled: boolean;
  draft_grace_time_ms: number;
  draft_reserve_time_ms: number;
  draft_timeout_action: TimeoutActionValue;
  hero_timer_enabled: boolean;
  hero_grace_time_ms: number;
  hero_reserve_time_ms: number;
};

export function draftSettingsFormToPatch(
  v: DraftSettingsFormValues,
): DraftSettingsPatch {
  return {
    ...draftOptionsFormToPatch({
      timer_enabled: v.draft_timer_enabled,
      grace_time_s: v.draft_grace_time_s,
      reserve_time_s: v.draft_reserve_time_s,
    }),
    hero_timer_enabled: v.hero_timer_enabled,
    hero_grace_time_ms: v.hero_grace_time_s * 1000,
    hero_reserve_time_ms: v.hero_reserve_time_s * 1000,
  };
}

export function draftSettingsFormToEventFields(
  v: DraftSettingsFormValues,
): EventDraftSettingsFields {
  const p = draftSettingsFormToPatch(v);
  return {
    draft_timer_enabled: p.timer_enabled,
    draft_grace_time_ms: p.grace_time_ms,
    draft_reserve_time_ms: p.reserve_time_ms,
    draft_timeout_action: v.draft_timeout_action,
    hero_timer_enabled: p.hero_timer_enabled,
    hero_grace_time_ms: p.hero_grace_time_ms,
    hero_reserve_time_ms: p.hero_reserve_time_ms,
  };
}

export function draftSettingsToFormInput(
  o: Partial<DraftOptions> | null | undefined,
): DraftSettingsFormValues {
  const d = { ...DRAFT_SETTINGS_DEFAULTS_MS, ...stripNullish(o ?? {}) };
  return {
    draft_timer_enabled: d.timer_enabled,
    draft_grace_time_s: d.grace_time_ms / 1000,
    draft_reserve_time_s: d.reserve_time_ms / 1000,
    draft_timeout_action: toTimeoutAction(d.timeout_action),
    hero_timer_enabled: d.hero_timer_enabled,
    hero_grace_time_s: d.hero_grace_time_ms / 1000,
    hero_reserve_time_s: d.hero_reserve_time_ms / 1000,
  };
}

export function eventFieldsToDraftSettingsFormInput(
  e:
    | Partial<Record<keyof EventDraftSettingsFields, unknown>>
    | null
    | undefined,
): DraftSettingsFormValues {
  const f = e ?? {};
  return draftSettingsToFormInput({
    timer_enabled: f.draft_timer_enabled as boolean | undefined,
    grace_time_ms: f.draft_grace_time_ms as number | undefined,
    reserve_time_ms: f.draft_reserve_time_ms as number | undefined,
    timeout_action: f.draft_timeout_action as string | undefined,
    hero_timer_enabled: f.hero_timer_enabled as boolean | undefined,
    hero_grace_time_ms: f.hero_grace_time_ms as number | undefined,
    hero_reserve_time_ms: f.hero_reserve_time_ms as number | undefined,
  });
}

function stripNullish<T extends object>(o: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(o).filter(([, v]) => v !== null && v !== undefined),
  ) as Partial<T>;
}

export const TeamDraftRoundSchema = z.object({
  pk: z.number().nullable(),
  draft: z.any(), // To be replaced with TeamDraftSchema
  captain: UserSchema.nullable(),
  pick_number: z.number().min(1).nullable(),
  pick_phase: z.number().min(1).nullable(),
  choice: UserSchema.nullable(),
  team: TeamSchema.nullable(),
  started_at: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  timed_out_at: z.string().nullable().optional(),
  grace_time_ms: z.number().nullable().optional(),
  pick_duration_ms: z.number().nullable().optional(),
  reserve_used_ms: z.number().nullable().optional(),
  skip_count: z.number().optional(),
});

// Use z.lazy() to avoid circular dependency with TournamentSchema
export const TeamDraftSchema = z.object({
  pk: z.number().nullable(),
  tournament: z.lazy(() => z.any()).nullable(), // Lazy reference to avoid circular import
  users_remaining: z.array(UserSchema).nullable(),
  draft_rounds: z.array(TeamDraftRoundSchema).nullable(),
  latest_round: z.number().nullable(),
  draft_style: z.enum(['snake', 'normal', 'shuffle']).default('snake'),
  snake_first_pick_mmr: z.number().default(0),
  snake_last_pick_mmr: z.number().default(0),
  normal_first_pick_mmr: z.number().default(0),
  normal_last_pick_mmr: z.number().default(0),
  current_draft_first_pick_mmr: z.number().default(0),
  current_draft_last_pick_mmr: z.number().default(0),
  state: TeamDraftStateSchema.optional(),
  clock_armed: z.boolean().optional(),
  paused_at: z.string().nullable().optional(),
  resuming_until: z.string().nullable().optional(),
  is_manual_pause: z.boolean().optional(),
  draft_options: DraftOptionsSchema.optional(),
});

TeamDraftRoundSchema.extend({ draft: TeamDraftSchema.nullable() });

// Backwards compatibility aliases
export const DraftSchema = TeamDraftSchema;
export const DraftRoundSchema = TeamDraftRoundSchema;
