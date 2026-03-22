/**
 * Approval Requirements config section for event create/edit modals.
 * Controls which rank types are allowed, screenshot requirements, and min MMR.
 */

import type { Control, UseFormWatch } from 'react-hook-form';
import { Checkbox } from '~/components/ui/checkbox';
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
          <FormField
            control={control}
            name="allow_active_mmr"
            render={({ field }) => (
              <FormItem className="flex items-center gap-3">
                <FormControl>
                  <Checkbox
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                </FormControl>
                <div>
                  <FormLabel className="text-sm font-medium">Active MMR Players</FormLabel>
                  <FormDescription className="text-xs">
                    Players with a current ranked medal
                  </FormDescription>
                </div>
              </FormItem>
            )}
          />

          {allowActiveMmr && (
            <div className="ml-7 space-y-3 border-l-2 border-primary/20 pl-4">
              <FormField
                control={control}
                name="discord_require_rank_screenshot"
                render={({ field }) => (
                  <FormItem className="flex items-center gap-3">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                    <div>
                      <FormLabel className="text-sm">Require MMR screenshot</FormLabel>
                      <FormDescription className="text-xs">
                        Player must upload a screenshot before signup completes
                      </FormDescription>
                    </div>
                  </FormItem>
                )}
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
          <FormField
            control={control}
            name="allow_previous_rank"
            render={({ field }) => (
              <FormItem className="flex items-center gap-3">
                <FormControl>
                  <Checkbox
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                </FormControl>
                <div>
                  <FormLabel className="text-sm font-medium">Previously Ranked Players</FormLabel>
                  <FormDescription className="text-xs">
                    Players who had a rank but are no longer active
                  </FormDescription>
                </div>
              </FormItem>
            )}
          />

          {allowPreviousRank && (
            <div className="ml-7 border-l-2 border-primary/20 pl-4">
              <FormField
                control={control}
                name="discord_require_rank_screenshot"
                render={({ field }) => (
                  <FormItem className="flex items-center gap-3">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                    <div>
                      <FormLabel className="text-sm">Require rank screenshot</FormLabel>
                      <FormDescription className="text-xs">
                        Player must upload a screenshot of their previous rank
                      </FormDescription>
                    </div>
                  </FormItem>
                )}
              />
            </div>
          )}
        </div>

        {/* Battle Cup (Never Ranked) */}
        <div className="rounded-lg border border-border p-4 space-y-3">
          <FormField
            control={control}
            name="allow_battlecup_rating"
            render={({ field }) => (
              <FormItem className="flex items-center gap-3">
                <FormControl>
                  <Checkbox
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                </FormControl>
                <div>
                  <FormLabel className="text-sm font-medium">Battle Cup Players (Never Ranked)</FormLabel>
                  <FormDescription className="text-xs">
                    Players who have never played ranked — use battle cup tier for estimation
                  </FormDescription>
                </div>
              </FormItem>
            )}
          />

          {allowBattlecupRating && (
            <div className="ml-7 border-l-2 border-primary/20 pl-4">
              <FormField
                control={control}
                name="discord_require_battlecup_screenshot"
                render={({ field }) => (
                  <FormItem className="flex items-center gap-3">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                    <div>
                      <FormLabel className="text-sm">Require battle cup screenshot</FormLabel>
                      <FormDescription className="text-xs">
                        Player must upload a screenshot of their battle cup ticket tier
                      </FormDescription>
                    </div>
                  </FormItem>
                )}
              />
            </div>
          )}
        </div>
      </div>

      {/* General Approval Settings */}
      <div className="space-y-4">
        <h4 className="text-sm font-semibold text-foreground">General Requirements</h4>

        <FormField
          control={control}
          name="require_steam_id"
          render={({ field }) => (
            <FormItem className="flex items-center gap-3">
              <FormControl>
                <Checkbox
                  checked={field.value}
                  onCheckedChange={field.onChange}
                />
              </FormControl>
              <div>
                <FormLabel className="text-sm">Require Friend ID</FormLabel>
                <FormDescription className="text-xs">
                  Player must provide their Dota 2 Friend ID
                </FormDescription>
              </div>
            </FormItem>
          )}
        />

        <FormField
          control={control}
          name="require_mmr_verified"
          render={({ field }) => (
            <FormItem className="flex items-center gap-3">
              <FormControl>
                <Checkbox
                  checked={field.value}
                  onCheckedChange={field.onChange}
                />
              </FormControl>
              <div>
                <FormLabel className="text-sm">Require verified MMR</FormLabel>
                <FormDescription className="text-xs">
                  Player must have admin-verified MMR on their org profile
                </FormDescription>
              </div>
            </FormItem>
          )}
        />

        <FormField
          control={control}
          name="require_profile_complete"
          render={({ field }) => (
            <FormItem className="flex items-center gap-3">
              <FormControl>
                <Checkbox
                  checked={field.value}
                  onCheckedChange={field.onChange}
                />
              </FormControl>
              <div>
                <FormLabel className="text-sm">Require complete profile</FormLabel>
                <FormDescription className="text-xs">
                  Player must have nickname, Steam ID, and Discord linked
                </FormDescription>
              </div>
            </FormItem>
          )}
        />
      </div>
    </div>
  );
}
