/**
 * Signup rules for every event, series and org-defaults form: when approved
 * players reach the tournament roster, and whether members may sign
 * themselves up. Every form schema merges signupRulesSchema (through
 * discordConfigSchema), so the narrowing cast below is sound.
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { ROLL_CALL_MODES, type signupRulesSchema } from './schemas';

type SignupRulesFields = z.input<typeof signupRulesSchema>;
type FlagName = 'roll_call_enabled' | 'allow_user_signups';

interface SignupRulesSectionProps<T extends FieldValues & SignupRulesFields> {
  control: Control<T>;
  modes?: readonly string[];
}

function FlagField({
  control,
  name,
  label,
  description,
}: {
  control: Control<SignupRulesFields>;
  name: FlagName;
  label: string;
  description?: string;
}) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className="flex items-center gap-3">
          <FormControl>
            <input
              type="checkbox"
              checked={!!field.value}
              onChange={field.onChange}
              data-testid={`signup-rules-${name}`}
              className="h-4 w-4 rounded border-border accent-primary"
            />
          </FormControl>
          <div>
            <FormLabel className="text-sm font-medium cursor-pointer">
              {label}
            </FormLabel>
            {description && (
              <FormDescription className="text-xs">
                {description}
              </FormDescription>
            )}
          </div>
        </FormItem>
      )}
    />
  );
}

export function SignupRulesSection<T extends FieldValues & SignupRulesFields>({
  control: parentControl,
  modes = ROLL_CALL_MODES,
}: SignupRulesSectionProps<T>) {
  const control = parentControl as unknown as Control<SignupRulesFields>;

  return (
    <div className="space-y-4" data-testid="signup-rules-section">
      <h4 className="text-sm font-semibold text-foreground">Signup Rules</h4>

      <FlagField
        control={control}
        name="roll_call_enabled"
        label="Players join the roster only after confirming"
        description="Approved players wait for roll-call confirmation before they are added to the tournament."
      />

      {modes.length > 1 && (
        <FormField
          control={control}
          name="roll_call_mode"
          render={({ field }) => (
            <FormItem className="ml-7">
              <FormLabel className="text-sm">Roll-call mode</FormLabel>
              <Select
                onValueChange={field.onChange}
                value={field.value ?? modes[0]}
              >
                <FormControl>
                  <SelectTrigger
                    className="w-40"
                    data-testid="roll-call-mode-select"
                  >
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {modes.map((mode) => (
                    <SelectItem key={mode} value={mode} className="capitalize">
                      {mode}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormItem>
          )}
        />
      )}

      <FlagField
        control={control}
        name="allow_user_signups"
        label="Members can sign themselves up"
        description="When off, only organizers can add players."
      />
    </div>
  );
}
