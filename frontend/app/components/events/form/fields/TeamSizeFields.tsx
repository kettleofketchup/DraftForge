import type { Control, FieldValues } from 'react-hook-form';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import type { EventFieldTestIds } from '../testIds';

export interface TeamSizeFieldValues {
  people_per_team: number;
  number_of_teams: number | null;
}

interface Props<T extends FieldValues & TeamSizeFieldValues> {
  control: Control<T>;
  testIds: Pick<EventFieldTestIds, 'peoplePerTeam' | 'maxTeams' | 'unlimited'>;
}

/** People Per Team plus Max Teams with its Unlimited (null) toggle. */
export function TeamSizeFields<T extends FieldValues & TeamSizeFieldValues>({
  control: parentControl,
  testIds,
}: Props<T>) {
  const control = parentControl as unknown as Control<TeamSizeFieldValues>;
  return (
    <>
      <FormField
        control={control}
        name="people_per_team"
        render={({ field }) => (
          <FormItem>
            <FormLabel>People Per Team</FormLabel>
            <FormControl>
              <Input
                data-testid={testIds.peoplePerTeam}
                type="number"
                min={1}
                {...field}
                onChange={(e) =>
                  field.onChange(parseInt(e.target.value, 10) || 1)
                }
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={control}
        name="number_of_teams"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Max Teams</FormLabel>
            <div className="flex items-center gap-2">
              <FormControl>
                <Input
                  data-testid={testIds.maxTeams}
                  type="number"
                  min={2}
                  disabled={field.value === null}
                  value={field.value ?? ''}
                  onChange={(e) => {
                    const v = parseInt(e.target.value, 10);
                    field.onChange(Number.isNaN(v) ? null : Math.max(2, v));
                  }}
                  placeholder="No limit"
                />
              </FormControl>
              <label className="flex cursor-pointer items-center gap-1.5 whitespace-nowrap text-xs text-muted-foreground">
                <input
                  data-testid={testIds.unlimited}
                  type="checkbox"
                  checked={field.value === null}
                  onChange={(e) => field.onChange(e.target.checked ? null : 2)}
                  className="h-3.5 w-3.5 rounded border-border accent-primary"
                />
                Unlimited
              </label>
            </div>
            <FormMessage />
          </FormItem>
        )}
      />
    </>
  );
}
