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
import type { EventFieldTestIds } from '../testIds';

interface OneOffFields {
  scheduled_at: string;
  event_ends_at?: string;
}

interface Props<T extends FieldValues & OneOffFields> {
  control: Control<T>;
  testIds: Pick<EventFieldTestIds, 'scheduled' | 'endsAt'>;
  showEndsAt: boolean;
  scheduledDescription?: string;
}

export function OneOffScheduleFields<T extends FieldValues & OneOffFields>({
  control: parentControl,
  testIds,
  showEndsAt,
  scheduledDescription,
}: Props<T>) {
  const control = parentControl as unknown as Control<OneOffFields>;
  const scheduled = (
    <FormField
      control={control}
      name="scheduled_at"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Scheduled Date &amp; Time</FormLabel>
          <FormControl>
            <Input
              data-testid={testIds.scheduled}
              type="datetime-local"
              {...field}
            />
          </FormControl>
          {scheduledDescription && (
            <FormDescription>{scheduledDescription}</FormDescription>
          )}
          <FormMessage />
        </FormItem>
      )}
    />
  );
  if (!showEndsAt) return scheduled;
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {scheduled}
      <FormField
        control={control}
        name="event_ends_at"
        render={({ field }) => (
          <FormItem>
            <FormLabel>End Date &amp; Time (optional)</FormLabel>
            <FormControl>
              <Input
                data-testid={testIds.endsAt}
                type="datetime-local"
                {...field}
                value={field.value ?? ''}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}
