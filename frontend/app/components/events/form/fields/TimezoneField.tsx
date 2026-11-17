import { Globe } from 'lucide-react';
import type { Control, FieldValues } from 'react-hook-form';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { EVENT_TIMEZONES, formatTimezoneLabel } from '~/lib/timezones';

interface TimezoneFields {
  timezone: string;
}

interface Props<T extends FieldValues & TimezoneFields> {
  control: Control<T>;
  label?: string;
  description?: string;
  triggerTestId?: string;
  /** Items get `${itemTestIdPrefix}${tz}`. */
  itemTestIdPrefix?: string;
  showIcon?: boolean;
  formatLabel?: (tz: string) => string;
  timezones?: readonly string[];
}

export function TimezoneField<T extends FieldValues & TimezoneFields>({
  control: parentControl,
  label = 'Timezone',
  description,
  triggerTestId,
  itemTestIdPrefix,
  showIcon = false,
  formatLabel = formatTimezoneLabel,
  timezones = EVENT_TIMEZONES,
}: Props<T>) {
  const control = parentControl as unknown as Control<TimezoneFields>;
  return (
    <FormField
      control={control}
      name="timezone"
      render={({ field }) => (
        <FormItem>
          <FormLabel
            className={showIcon ? 'flex items-center gap-2' : undefined}
          >
            {showIcon && <Globe className="h-4 w-4" />}
            {label}
          </FormLabel>
          <Select onValueChange={field.onChange} value={field.value}>
            <FormControl>
              <SelectTrigger data-testid={triggerTestId} className="w-full">
                <SelectValue placeholder="Select timezone" />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {timezones.map((tz) => (
                <SelectItem
                  key={tz}
                  value={tz}
                  data-testid={
                    itemTestIdPrefix ? `${itemTestIdPrefix}${tz}` : undefined
                  }
                >
                  {formatLabel(tz)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {description && <FormDescription>{description}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
