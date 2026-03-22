/**
 * Approval Requirements config section for event create/edit modals.
 * Controls which rank types are allowed, screenshot requirements, and min MMR.
 */

import type { Control, UseFormWatch } from 'react-hook-form';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';

interface ApprovalConfigSectionProps {
  control: Control<any>;
  watch: UseFormWatch<any>;
}

/** Reusable checkbox field matching DiscordConfigSection pattern */
function CheckboxField({ control, name, label, description }: {
  control: Control<any>;
  name: string;
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
              checked={field.value}
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

export function ApprovalConfigSection({ control, watch }: ApprovalConfigSectionProps) {
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
