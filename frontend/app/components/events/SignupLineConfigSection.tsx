/**
 * Line-order rules for every event, series and org-defaults form. Every form
 * schema merges signupLineSchema (through discordConfigSchema), so the
 * narrowing cast below is sound.
 */

import type { Control, FieldValues } from 'react-hook-form';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from '~/components/ui/form';
import type { SignupLineFields } from './schemas';

const RULES: ReadonlyArray<{
  name: keyof SignupLineFields;
  label: string;
  description: string;
}> = [
  {
    name: 'line_withdraw_forfeits',
    label: 'Withdrawing gives up your place',
    description:
      'A member who withdraws, declines or is rejected and signs up again goes to the back of the line. When off, they get their old place back.',
  },
  {
    name: 'line_switch_restamps',
    label: 'Switching Main/Maybe gives up your place',
    description:
      'Moving between Main and Maybe sends the signup to the back of the line. When off, it keeps its place.',
  },
];

interface SignupLineConfigSectionProps<
  T extends FieldValues & SignupLineFields,
> {
  control: Control<T>;
}

export function SignupLineConfigSection<
  T extends FieldValues & SignupLineFields,
>({ control: parentControl }: SignupLineConfigSectionProps<T>) {
  const control = parentControl as unknown as Control<SignupLineFields>;

  return (
    <div className="space-y-4" data-testid="signup-line-section">
      <h4 className="text-sm font-semibold text-foreground">Signup Line</h4>
      {RULES.map((rule) => (
        <FormField
          key={rule.name}
          control={control}
          name={rule.name}
          render={({ field }) => (
            <FormItem className="flex items-center gap-3">
              <FormControl>
                <input
                  type="checkbox"
                  checked={!!field.value}
                  onChange={field.onChange}
                  data-testid={`signup-line-${rule.name}`}
                  className="h-4 w-4 rounded border-border accent-primary"
                />
              </FormControl>
              <div>
                <FormLabel className="text-sm font-medium cursor-pointer">
                  {rule.label}
                </FormLabel>
                <FormDescription className="text-xs">
                  {rule.description}
                </FormDescription>
              </div>
            </FormItem>
          )}
        />
      ))}
    </div>
  );
}
