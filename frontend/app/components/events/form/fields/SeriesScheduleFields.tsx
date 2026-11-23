import type { Control, FieldValues } from 'react-hook-form';
import { IntegerInput } from '~/components/patterns/IntegerInput';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { cn } from '~/lib/utils';
import { DAY_LABELS, FREQUENCY_LABELS } from '../../schemas';

interface SeriesFields {
  frequency?: string;
  day_of_week?: number;
  time_of_day?: string;
  starts_at?: string;
  ends_at?: string;
  generate_days_ahead: number;
}

interface Props<T extends FieldValues & SeriesFields> {
  control: Control<T>;
  /** Controls get `${testIdPrefix}-frequency-select`, `-day-select`, … */
  testIdPrefix: string;
  showStartsAt: boolean;
}

/** Repeating schedule: frequency, day, time, date range and look-ahead. */
export function SeriesScheduleFields<T extends FieldValues & SeriesFields>({
  control: parentControl,
  testIdPrefix: p,
  showStartsAt,
}: Props<T>) {
  const control = parentControl as unknown as Control<SeriesFields>;
  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormField
          control={control}
          name="frequency"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Frequency</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger
                    data-testid={`${p}-frequency-select`}
                    className="w-full"
                  >
                    <SelectValue placeholder="Select frequency" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {Object.entries(FREQUENCY_LABELS).map(([val, label]) => (
                    <SelectItem
                      key={val}
                      value={val}
                      data-testid={`${p}-frequency-option-${val}`}
                    >
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={control}
          name="day_of_week"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Day of Week</FormLabel>
              <Select
                onValueChange={(val) => field.onChange(parseInt(val, 10))}
                value={field.value?.toString()}
              >
                <FormControl>
                  <SelectTrigger
                    data-testid={`${p}-day-select`}
                    className="w-full"
                  >
                    <SelectValue placeholder="Select day" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {DAY_LABELS.map((label, idx) => (
                    <SelectItem
                      key={label}
                      value={String(idx)}
                      data-testid={`${p}-day-option-${idx}`}
                    >
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      <div
        className={cn(
          'grid grid-cols-1 gap-4',
          showStartsAt ? 'sm:grid-cols-3' : 'sm:grid-cols-2',
        )}
      >
        <FormField
          control={control}
          name="time_of_day"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Time</FormLabel>
              <FormControl>
                <Input data-testid={`${p}-time-input`} type="time" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        {showStartsAt && (
          <FormField
            control={control}
            name="starts_at"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Starts</FormLabel>
                <FormControl>
                  <Input
                    data-testid={`${p}-starts-input`}
                    type="date"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}
        <FormField
          control={control}
          name="ends_at"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Ends (optional)</FormLabel>
              <FormControl>
                <Input data-testid={`${p}-ends-input`} type="date" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      <FormField
        control={control}
        name="generate_days_ahead"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Generate Days Ahead</FormLabel>
            <FormControl>
              <IntegerInput
                data-testid={`${p}-generate-days-input`}
                min={1}
                name={field.name}
                ref={field.ref}
                onBlur={field.onBlur}
                value={field.value}
                onValueChange={(v) => v != null && field.onChange(v)}
              />
            </FormControl>
            <FormDescription>
              How many days in advance to generate events
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
    </>
  );
}
