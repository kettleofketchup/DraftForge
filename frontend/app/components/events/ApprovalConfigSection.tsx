/**
 * Approval Requirements config section for event create/edit modals.
 * Controls which rank types are allowed, screenshot requirements, and min MMR.
 * The rank types and verified MMR are Dota-only: other games hide them and keep
 * the stored values.
 *
 * Shared by the event forms; their schemas `.merge(discordConfigSchema)`, so any
 * generic T extending z.input<typeof discordConfigSchema> is accepted.
 *
 * One narrowing cast at the top (`as unknown as Control<ApprovalFields>`) lets
 * the body reference `name="allow_active_mmr"` etc. with full type checking —
 * a typo'd name is a compile error rather than silent dead UI.
 */

import { useWatch, type Control, type FieldValues } from 'react-hook-form';
import type { z } from 'zod';
import { GAME_TYPE } from '~/components/game/constants';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import type { discordConfigSchema } from './schemas';

type ApprovalFields = z.input<typeof discordConfigSchema> & {
  game_type: number;
};

interface ApprovalConfigSectionProps<T extends FieldValues & ApprovalFields> {
  control: Control<T>;
}

/** Reusable checkbox field bound to a known approval field name. */
function CheckboxField({
  control,
  name,
  label,
  description,
}: {
  control: Control<ApprovalFields>;
  name: Extract<keyof ApprovalFields, string>;
  label: string;
  description: string;
}) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className="flex items-start gap-3 space-y-0">
          <FormControl>
            <input
              type="checkbox"
              checked={!!field.value}
              onChange={field.onChange}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-border accent-primary"
            />
          </FormControl>
          <div>
            <FormLabel className="text-sm font-medium cursor-pointer">
              {label}
            </FormLabel>
            <FormDescription className="text-xs">{description}</FormDescription>
          </div>
        </FormItem>
      )}
    />
  );
}

export function ApprovalConfigSection<T extends FieldValues & ApprovalFields>({
  control: parentControl,
}: ApprovalConfigSectionProps<T>) {
  // T extends ApprovalFields by the generic constraint, so narrowing to
  // Control<ApprovalFields> is sound: we touch only the discord-config slice
  // of the parent form, never the parent's extra keys.
  const control = parentControl as unknown as Control<ApprovalFields>;

  const isDota = useWatch({ control, name: 'game_type' }) === GAME_TYPE.DOTA2;
  const allowActiveMmr = useWatch({ control, name: 'allow_active_mmr' });
  const allowBattlecupRating = useWatch({
    control,
    name: 'allow_battlecup_rating',
  });

  return (
    <div className="space-y-6">
      {/* Rank Type Restrictions */}
      {isDota && (
        <div className="space-y-4">
          <div>
            <h4 className="text-sm font-semibold text-foreground">
              Allowed Rank Types
            </h4>
            <p className="text-xs text-muted-foreground mt-1">
              Control which Dota 2 rank categories can sign up for this event.
            </p>
          </div>

          {/* Active MMR */}
          <div className="rounded-lg border border-border p-4 space-y-3">
            <CheckboxField
              control={control}
              name="allow_active_mmr"
              label="Active MMR Players"
              description="Players with a current ranked medal"
            />
            {allowActiveMmr && (
              <div className="ml-7 space-y-3">
                <CheckboxField
                  control={control}
                  name="discord_require_rank_screenshot"
                  label="Require MMR screenshot"
                  description="Player must upload a screenshot before signup completes"
                />
                <FormField
                  control={control}
                  name="min_mmr"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-sm">Minimum MMR</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={0}
                          max={20000}
                          placeholder="No minimum"
                          value={field.value ?? ''}
                          onChange={(e) => {
                            const v = e.target.value;
                            field.onChange(v === '' ? null : parseInt(v, 10));
                          }}
                          className="w-40"
                        />
                      </FormControl>
                      <FormDescription className="text-xs">
                        Players below this MMR will need admin approval
                      </FormDescription>
                    </FormItem>
                  )}
                />
              </div>
            )}
          </div>

          {/* Previous Rank */}
          <div className="rounded-lg border border-border p-4 space-y-3">
            <CheckboxField
              control={control}
              name="allow_previous_rank"
              label="Previously Ranked Players"
              description="Players who had a rank but are no longer active"
            />
          </div>

          {/* Battle Cup (Never Ranked) */}
          <div className="rounded-lg border border-border p-4 space-y-3">
            <CheckboxField
              control={control}
              name="allow_battlecup_rating"
              label="Battle Cup Players (Never Ranked)"
              description="Players who have never played ranked — use battle cup tier for estimation"
            />
            {allowBattlecupRating && (
              <div className="ml-7">
                <CheckboxField
                  control={control}
                  name="discord_require_battlecup_screenshot"
                  label="Require battle cup screenshot"
                  description="Player must upload a screenshot of their battle cup ticket tier"
                />
              </div>
            )}
          </div>
        </div>
      )}

      {/* General Approval Settings */}
      <div className="space-y-4">
        <h4 className="text-sm font-semibold text-foreground">
          General Requirements
        </h4>

        <CheckboxField
          control={control}
          name="require_steam_id"
          label="Require Friend ID"
          description="Player must provide their Steam Friend ID"
        />

        {isDota && (
          <CheckboxField
            control={control}
            name="require_mmr_verified"
            label="Require verified MMR"
            description="Player must have admin-verified MMR on their org profile"
          />
        )}

        <CheckboxField
          control={control}
          name="require_profile_complete"
          label="Require complete profile"
          description="Player must have nickname, Steam ID, and Discord linked"
        />
      </div>
    </div>
  );
}
