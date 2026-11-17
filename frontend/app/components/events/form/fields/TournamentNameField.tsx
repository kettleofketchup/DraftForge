import type { Control, FieldValues } from 'react-hook-form';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';

interface TournamentNameFields {
  tournament_name: string;
}

interface Props<T extends FieldValues & TournamentNameFields> {
  control: Control<T>;
  testId: string;
  label?: string;
  placeholder?: string;
  description?: string;
}

export function TournamentNameField<
  T extends FieldValues & TournamentNameFields,
>({
  control: parentControl,
  testId,
  label = 'Tournament Name',
  placeholder,
  description,
}: Props<T>) {
  const control = parentControl as unknown as Control<TournamentNameFields>;
  return (
    <FormField
      control={control}
      name="tournament_name"
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input data-testid={testId} placeholder={placeholder} {...field} />
          </FormControl>
          {description && <FormDescription>{description}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
