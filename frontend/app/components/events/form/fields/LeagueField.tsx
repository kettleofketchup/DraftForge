import type { Control, FieldValues } from 'react-hook-form';
import { LeagueCombobox } from '~/components/league/LeagueCombobox';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import type { LeagueTestIds } from '../testIds';

interface LeagueFields {
  tournament_league?: number | null;
}

interface Props<T extends FieldValues & LeagueFields> {
  control: Control<T>;
  organizationId: number | undefined;
  testIds: LeagueTestIds;
}

export function LeagueField<T extends FieldValues & LeagueFields>({
  control: parentControl,
  organizationId,
  testIds,
}: Props<T>) {
  const control = parentControl as unknown as Control<LeagueFields>;
  return (
    <FormField
      control={control}
      name="tournament_league"
      render={({ field, fieldState }) => (
        <FormItem>
          <FormLabel>League</FormLabel>
          <FormControl>
            <LeagueCombobox
              organizationId={organizationId}
              value={field.value ?? null}
              onChange={(v) => field.onChange(v)}
              invalid={!!fieldState.error}
              triggerTestId={testIds.trigger}
              itemTestIdPrefix={testIds.itemPrefix}
              searchTestId={testIds.search}
              clearTestId={testIds.clear}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
