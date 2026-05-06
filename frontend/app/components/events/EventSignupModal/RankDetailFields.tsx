'use client';
import { type Control, useWatch } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormMessage } from '~/components/ui/form';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '~/components/ui/select';

const MEDALS = ['Herald', 'Guardian', 'Crusader', 'Archon', 'Legend', 'Ancient', 'Divine', 'Immortal'];
const STARS = ['1', '2', '3', '4', '5'];
const BC_TIERS = ['1', '2', '3', '4', '5', '6', '7', '8'];

export function RankDetailFields({ control }: { control: Control }) {
  const rankStatus = useWatch({ control, name: 'rank_status' });

  if (rankStatus === 'never') {
    return (
      <FormField
        key="bc"
        control={control}
        name="battle_cup_tier"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Battle Cup Tier</FormLabel>
            <FormControl>
              <Select
                key={rankStatus}
                value={field.value != null ? String(field.value) : ''}
                onValueChange={(v) => field.onChange(parseInt(v, 10))}
              >
                <SelectTrigger data-testid="signup-battlecup-tier" className="min-h-11">
                  <SelectValue placeholder="Select tier" />
                </SelectTrigger>
                <SelectContent>
                  {BC_TIERS.map((t) => <SelectItem key={t} value={t}>Tier {t}</SelectItem>)}
                </SelectContent>
              </Select>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    );
  }

  if (rankStatus !== 'active' && rankStatus !== 'previous') return null;

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <FormField
        key="medal"
        control={control}
        name="rank_medal_medal"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Medal</FormLabel>
            <FormControl>
              <Select key={rankStatus} value={field.value ?? ''} onValueChange={field.onChange}>
                <SelectTrigger data-testid="signup-rank-medal" className="min-h-11">
                  <SelectValue placeholder="Select medal" />
                </SelectTrigger>
                <SelectContent>
                  {MEDALS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        key="star"
        control={control}
        name="rank_medal_star"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Star</FormLabel>
            <FormControl>
              <Select key={rankStatus} value={field.value ?? ''} onValueChange={field.onChange}>
                <SelectTrigger data-testid="signup-rank-star" className="min-h-11">
                  <SelectValue placeholder="Star (1-5)" />
                </SelectTrigger>
                <SelectContent>
                  {STARS.map((s) => <SelectItem key={s} value={s}>Star {s}</SelectItem>)}
                </SelectContent>
              </Select>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}
