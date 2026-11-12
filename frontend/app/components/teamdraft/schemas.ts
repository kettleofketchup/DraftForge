import { z } from 'zod';
import { TickEnvelopeSchema } from '~/lib/draftClock';
import { TeamSchema } from '../team/schemas';
import { UserSchema } from '../user/schemas';

export const TeamDraftStateSchema = z.enum(['pending', 'drafting', 'paused', 'resuming', 'completed']);
export type TeamDraftState = z.infer<typeof TeamDraftStateSchema>;

export const DraftOptionsSchema = z.object({
  timer_enabled: z.boolean(),
  grace_time_ms: z.number().int(),
  reserve_time_ms: z.number().int(),
  timeout_action: z.string(),
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
          .min(min, min === 0 ? 'Cannot be negative' : `At least ${min} second`),
      ),
  );

export const DraftOptionsFormSchema = z.object({
  timer_enabled: z.boolean(),
  grace_time_s: wholeSeconds(1),
  reserve_time_s: wholeSeconds(0),
});
export type DraftOptionsFormInput = z.input<typeof DraftOptionsFormSchema>;
export type DraftOptionsFormValues = z.output<typeof DraftOptionsFormSchema>;
export type DraftOptionsPatch = { timer_enabled: boolean; grace_time_ms: number; reserve_time_ms: number };

export function draftOptionsFormToPatch(v: DraftOptionsFormValues): DraftOptionsPatch {
  return {
    timer_enabled: v.timer_enabled,
    grace_time_ms: v.grace_time_s * 1000,
    reserve_time_ms: v.reserve_time_s * 1000,
  };
}

export function draftOptionsToFormInput(o: DraftOptions | null | undefined): DraftOptionsFormInput {
  if (!o) return { timer_enabled: true, grace_time_s: 30, reserve_time_s: 30 };
  return {
    timer_enabled: o.timer_enabled,
    grace_time_s: o.grace_time_ms / 1000,
    reserve_time_s: o.reserve_time_ms / 1000,
  };
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
