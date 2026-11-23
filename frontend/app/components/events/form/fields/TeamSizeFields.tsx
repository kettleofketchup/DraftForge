import type { Control, FieldValues } from 'react-hook-form';
import { IntegerInput } from '~/components/patterns/IntegerInput';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
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
              <IntegerInput
                data-testid={testIds.peoplePerTeam}
                min={1}
                name={field.name}
                ref={field.ref}
                onBlur={field.onBlur}
                value={field.value}
                onValueChange={(v) => v != null && field.onChange(v)}
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
                <IntegerInput
                  data-testid={testIds.maxTeams}
                  min={2}
                  disabled={field.value === null}
                  name={field.name}
                  ref={field.ref}
                  onBlur={field.onBlur}
                  value={field.value}
                  onValueChange={(v) => v != null && field.onChange(v)}
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
