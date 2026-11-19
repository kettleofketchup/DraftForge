/**
 * Self sign-up rule for every event, series and org-defaults form. The
 * roster rule (roll call) lives in ReadyCheckConfigSection. Every form schema
 * merges signupRulesSchema (through discordConfigSchema), so the narrowing
 * cast below is sound.
 */

import type { Control, FieldValues } from 'react-hook-form';
import type { z } from 'zod';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from '~/components/ui/form';
import type { signupRulesSchema } from './schemas';

type SignupRulesFields = z.input<typeof signupRulesSchema>;

interface SignupRulesSectionProps<T extends FieldValues & SignupRulesFields> {
  control: Control<T>;
}

export function SignupRulesSection<T extends FieldValues & SignupRulesFields>({
  control: parentControl,
}: SignupRulesSectionProps<T>) {
  const control = parentControl as unknown as Control<SignupRulesFields>;

  return (
    <div className="space-y-4" data-testid="signup-rules-section">
      <h4 className="text-sm font-semibold text-foreground">Signup Rules</h4>
      <FormField
        control={control}
        name="allow_user_signups"
        render={({ field }) => (
          <FormItem className="flex items-center gap-3">
            <FormControl>
              <input
                type="checkbox"
                checked={!!field.value}
                onChange={field.onChange}
                data-testid="signup-rules-allow_user_signups"
                className="h-4 w-4 rounded border-border accent-primary"
              />
            </FormControl>
            <div>
              <FormLabel className="text-sm font-medium cursor-pointer">
                Members can sign themselves up
              </FormLabel>
              <FormDescription className="text-xs">
                When off, only organizers can add players.
              </FormDescription>
            </div>
          </FormItem>
        )}
      />
    </div>
  );
}
