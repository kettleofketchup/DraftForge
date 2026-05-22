/**
 * Approval Requirements config section for event create/edit modals.
 * Controls which rank types are allowed, screenshot requirements, and min MMR.
 *
 * Shared across CreateEventModal, EditEventModal, EditOrgDefaultsModal, and
 * EditRepeaterModal — all four schemas `.merge(discordConfigSchema)`, so any
 * generic T extending z.input<typeof discordConfigSchema> is accepted.
 *
 * One narrowing cast at the top (`as unknown as Control<ApprovalFields>`) lets
 * the body reference `name="allow_active_mmr"` etc. with full type checking —
 * a typo'd name is a compile error rather than silent dead UI.
 */

import type { Control, FieldValues, UseFormWatch } from 'react-hook-form';
import type { z } from 'zod';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import type { discordConfigSchema } from './schemas';

type ApprovalFields = z.input<typeof discordConfigSchema>;

interface ApprovalConfigSectionProps<T extends FieldValues & ApprovalFields> {
  control: Control<T>;
  watch: UseFormWatch<T>;
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
        <FormItem className="flex items-center gap-3">
          <FormControl>
            <input
              type="checkbox"
              checked={!!field.value}
              onChange={field.onChange}
              className="h-4 w-4 rounded border-border accent-primary"
            />
          </FormControl>
          <div>
            <FormLabel className="text-sm font-medium cursor-pointer">{label}</FormLabel>
            <FormDescription className="text-xs">{description}</FormDescription>
          </div>
        </FormItem>
      )}
    />
  );
}

export function ApprovalConfigSection<T extends FieldValues & ApprovalFields>({
  control: parentControl,
  watch: parentWatch,
}: ApprovalConfigSectionProps<T>) {
  // T extends ApprovalFields by the generic constraint, so narrowing to
  // Control<ApprovalFields> is sound: we touch only the discord-config slice
  // of the parent form, never the parent's extra keys.
  const control = parentControl as unknown as Control<ApprovalFields>;
  const watch = parentWatch as unknown as UseFormWatch<ApprovalFields>;

  const allowActiveMmr = watch('allow_active_mmr');
  const allowPreviousRank = watch('allow_previous_rank');
  const allowBattlecupRating = watch('allow_battlecup_rating');

  return (
    <div className="space-y-6">
      {/* Rank Type Restrictions */}
      <div className="space-y-4">
        <div>
          <h4 className="text-sm font-semibold text-foreground">Allowed Rank Types</h4>
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
            <div className="ml-7 space-y-3 border-l-2 border-primary/20 pl-4">
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
          {allowPreviousRank && (
            <div className="ml-7 border-l-2 border-primary/20 pl-4">
              <CheckboxField
                control={control}
                name="discord_require_rank_screenshot"
                label="Require rank screenshot"
                description="Player must upload a screenshot of their previous rank"
              />
            </div>
          )}
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
            <div className="ml-7 border-l-2 border-primary/20 pl-4">
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

      {/* General Approval Settings */}
      <div className="space-y-4">
        <h4 className="text-sm font-semibold text-foreground">General Requirements</h4>

        <CheckboxField
          control={control}
          name="require_steam_id"
          label="Require Friend ID"
          description="Player must provide their Dota 2 Friend ID"
        />

        <CheckboxField
          control={control}
          name="require_mmr_verified"
          label="Require verified MMR"
          description="Player must have admin-verified MMR on their org profile"
        />

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
