'use client';
import { type Control } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormMessage } from '~/components/ui/form';
import { ToggleGroup, ToggleGroupItem } from '~/components/ui/toggle-group';

const POSITIONS: Array<{ value: string; label: string; emoji: string }> = [
  { value: '1', label: 'Carry',         emoji: '\u{2694}\u{FE0F}' },
  { value: '2', label: 'Mid',           emoji: '\u{1F3AF}' },
  { value: '3', label: 'Offlane',       emoji: '\u{1F6E1}\u{FE0F}' },
  { value: '4', label: 'Soft Support',  emoji: '\u{1F49A}' },
  { value: '5', label: 'Hard Support',  emoji: '\u{1F49B}' },
];

export function PositionPickerGrid({ control }: { control: Control }) {
  return (
    <FormField
      control={control}
      name="positions"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Preferred Positions</FormLabel>
          <FormControl>
            <ToggleGroup
              type="multiple"
              data-testid="signup-positions"
              aria-label="Preferred positions"
              value={(field.value ?? []).map(String)}
              onValueChange={(values: string[]) => field.onChange(values.map(Number))}
              className="grid grid-cols-5 gap-2"
            >
              {POSITIONS.map((p) => (
                <ToggleGroupItem
                  key={p.value}
                  value={p.value}
                  className="min-h-11 flex flex-col items-center"
                >
                  <span aria-hidden="true">{p.emoji}</span>
                  <span className="text-xs">{p.label}</span>
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
