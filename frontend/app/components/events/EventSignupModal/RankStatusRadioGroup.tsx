'use client';
import { CheckCircle2 } from 'lucide-react';
import { type Control } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormMessage } from '~/components/ui/form';
import { RadioGroup, RadioGroupItem } from '~/components/ui/radio-group';
import { cn } from '~/lib/utils';

type Option = { value: 'active' | 'previous' | 'never'; label: string; desc: string };

const ALL_OPTIONS: Array<Option & { flag: 'allow_active_mmr' | 'allow_previous_rank' | 'allow_battlecup_rating' }> = [
  { value: 'active',   flag: 'allow_active_mmr',      label: 'I have an active MMR', desc: 'Currently ranked in Dota 2' },
  { value: 'previous', flag: 'allow_previous_rank',   label: 'I had an MMR',          desc: 'Previously ranked but not currently' },
  { value: 'never',    flag: 'allow_battlecup_rating',label: "I've never had an MMR", desc: 'Never played ranked Dota 2' },
];

type EventFlags = {
  allow_active_mmr: boolean;
  allow_previous_rank: boolean;
  allow_battlecup_rating: boolean;
};

export function RankStatusRadioGroup({
  control,
  event,
}: {
  control: Control;
  event: EventFlags;
}) {
  const opts = ALL_OPTIONS.filter((o) => event[o.flag]);
  return (
    <FormField
      control={control}
      name="rank_status"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Rank Status</FormLabel>
          <FormControl>
            <RadioGroup
              data-testid="signup-rank-status"
              value={field.value ?? ''}
              onValueChange={field.onChange}
              className="flex flex-col gap-2"
            >
              {opts.map((o) => {
                const selected = field.value === o.value;
                return (
                  <label
                    key={o.value}
                    data-testid={`signup-rank-status-${o.value}`}
                    className={cn(
                      // ring-inset keeps the highlight inside the card's box —
                      // the modal body scrolls (overflow-y-auto) and an outside
                      // ring on a top-edge card gets visually clipped.
                      'flex items-start gap-3 rounded-md border p-3 transition-colors',
                      'hover:bg-accent cursor-pointer min-h-11',
                      'border-border',
                      'focus-within:ring-2 focus-within:ring-inset focus-within:ring-ring',
                      selected && 'ring-2 ring-inset ring-ring border-ring bg-accent/40',
                    )}
                  >
                    {/* The actual radio control stays in the DOM (a11y +
                        keyboard nav) but is visually hidden — a small h-4 w-4
                        circle reads as an unrendered rectangle on a dark
                        background. We show a CheckCircle instead so the
                        selected state is obvious. */}
                    <RadioGroupItem value={o.value} className="sr-only" />
                    <CheckCircle2
                      aria-hidden="true"
                      className={cn(
                        'mt-0.5 h-5 w-5 shrink-0 transition-colors',
                        selected ? 'text-primary' : 'text-muted-foreground/40',
                      )}
                    />
                    <div className="flex flex-col">
                      <span className="font-medium">{o.label}</span>
                      <span className="text-sm text-muted-foreground">{o.desc}</span>
                    </div>
                  </label>
                );
              })}
            </RadioGroup>
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
