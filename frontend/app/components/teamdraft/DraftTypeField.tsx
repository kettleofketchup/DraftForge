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
import { DRAFT_STYLE_LABELS, DRAFT_STYLE_VALUES } from './schemas';

interface DraftTypeFields {
  draft_type: string;
}

interface DraftTypeFieldProps<T extends FieldValues & DraftTypeFields> {
  control: Control<T>;
  label?: string;
  description?: string;
  /** Trigger testid; items get `${testId}-${value}`. */
  testId?: string;
}

export function DraftTypeField<T extends FieldValues & DraftTypeFields>({
  control: parentControl,
  label = 'Draft Type',
  description,
  testId,
}: DraftTypeFieldProps<T>) {
  const control = parentControl as unknown as Control<DraftTypeFields>;
  return (
    <FormField
      control={control}
      name="draft_type"
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <Select onValueChange={field.onChange} value={field.value}>
            <FormControl>
              <SelectTrigger data-testid={testId} className="w-full">
                <SelectValue />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {DRAFT_STYLE_VALUES.map((v) => (
                <SelectItem
                  key={v}
                  value={v}
                  data-testid={testId ? `${testId}-${v}` : undefined}
                >
                  {DRAFT_STYLE_LABELS[v]}
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
