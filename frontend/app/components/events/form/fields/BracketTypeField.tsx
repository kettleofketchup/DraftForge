import type { Control, FieldValues } from 'react-hook-form';
import type { TournamentTypeValue } from '~/components/tournament/schemas';
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

interface BracketFields {
  tournament_type: string;
}

const DEFAULT_LABELS: Record<TournamentTypeValue, string> = {
  double_elimination: 'Double Elimination',
  single_elimination: 'Single Elimination',
  swiss: 'Swiss Bracket',
};

const DEFAULT_ORDER: readonly TournamentTypeValue[] = [
  'double_elimination',
  'single_elimination',
  'swiss',
];

interface Props<T extends FieldValues & BracketFields> {
  control: Control<T>;
  label?: string;
  /** null hides the description. */
  description?: string | null;
  placeholder?: string;
  triggerTestId?: string;
  /** Defaults to `${triggerTestId}-option-${value}` when triggerTestId is set. */
  itemTestIds?: Partial<Record<TournamentTypeValue, string>>;
  optionLabels?: Partial<Record<TournamentTypeValue, string>>;
  order?: readonly TournamentTypeValue[];
}

export function BracketTypeField<T extends FieldValues & BracketFields>({
  control: parentControl,
  label = 'Bracket Type',
  description = 'Double elimination works best with teams that are a power of 2 (2, 4, 8, 16)',
  placeholder,
  triggerTestId,
  itemTestIds,
  optionLabels,
  order = DEFAULT_ORDER,
}: Props<T>) {
  const control = parentControl as unknown as Control<BracketFields>;
  const labels = { ...DEFAULT_LABELS, ...optionLabels };
  const itemTestId = (v: TournamentTypeValue) =>
    itemTestIds?.[v] ??
    (triggerTestId ? `${triggerTestId}-option-${v}` : undefined);
  return (
    <FormField
      control={control}
      name="tournament_type"
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <Select onValueChange={field.onChange} value={field.value}>
            <FormControl>
              <SelectTrigger data-testid={triggerTestId} className="w-full">
                <SelectValue placeholder={placeholder} />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {order.map((v) => (
                <SelectItem key={v} value={v} data-testid={itemTestId(v)}>
                  {labels[v]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {description && field.value === 'double_elimination' && (
            <FormDescription>{description}</FormDescription>
          )}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
