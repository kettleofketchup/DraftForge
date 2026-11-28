/**
 * Line-order rules, spot transfer and the staff reason policy for every event, series and
 * org-defaults form. Every form schema merges signupLineSchema (through
 * discordConfigSchema), so the narrowing cast below is sound.
 */

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
import { EVENT_SECTION_FIELDS } from './form/settingsFields';
import {
  STAFF_REASON_POLICIES,
  STAFF_REASON_POLICY_LABELS,
  type SignupLineFields,
} from './schemas';

type LineRuleField =
  | 'line_withdraw_forfeits'
  | 'line_switch_restamps'
  | 'allow_spot_transfer';

const RULES: ReadonlyArray<{
  name: LineRuleField;
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
  {
    name: 'allow_spot_transfer',
    label: 'Allow spot transfer',
    description:
      'Members can give their place to another eligible member. If that member already has a place, the two swap.',
  },
];

const STAFF_REASON_META = EVENT_SECTION_FIELDS.approval.staff_reason_policy;
const STAFF_REASON_TEST_ID = 'signup-line-staff_reason_policy';

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
      <FormField
        control={control}
        name="staff_reason_policy"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{STAFF_REASON_META.label}</FormLabel>
            {/* Bare Select, not BrandSelect: matches the neutral selects in these dialogs (component-substitutions.md exception). */}
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger
                  className="w-full"
                  data-testid={STAFF_REASON_TEST_ID}
                >
                  <SelectValue />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {STAFF_REASON_POLICIES.map((policy) => (
                  <SelectItem
                    key={policy}
                    value={policy}
                    data-testid={`${STAFF_REASON_TEST_ID}-${policy}`}
                  >
                    {STAFF_REASON_POLICY_LABELS[policy]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FormDescription className="text-xs">
              {STAFF_REASON_META.description}
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}
