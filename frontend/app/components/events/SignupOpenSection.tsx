/**
 * When signups open, for every event, series and org-defaults form. The form
 * stores hours (the API field); staff edit whole days. Every form schema
 * merges signupOpenSchema, so the narrowing cast below is sound.
 */

import { useEffect, useId, useRef, useState } from 'react';
import type {
  Control,
  ControllerRenderProps,
  FieldValues,
} from 'react-hook-form';
import { useController, useWatch } from 'react-hook-form';
import type { z } from 'zod';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { RadioGroup, RadioGroupItem } from '~/components/ui/radio-group';
import {
  MAX_SIGNUPS_OPEN_HOURS_BEFORE,
  SIGNUP_OPEN_DEFAULTS,
  type SignupOpenMode,
  signupOpenSchema,
} from './schemas';

type SignupOpenFields = z.input<typeof signupOpenSchema>;

const HOURS_PER_DAY = 24;
const MAX_DAYS = MAX_SIGNUPS_OPEN_HOURS_BEFORE / HOURS_PER_DAY;

const isValidHours = (hours: unknown): hours is number =>
  signupOpenSchema.shape.signups_open_hours_before.safeParse(hours).success;

const daysText = (hours: number | undefined): string =>
  String(Math.round((hours ?? 0) / HOURS_PER_DAY));

export const SIGNUP_OPEN_OPTIONS: readonly {
  mode: SignupOpenMode;
  label: string;
}[] = [
  { mode: 'manual', label: 'Open manually' },
  { mode: 'immediate', label: 'Open immediately' },
  { mode: 'scheduled', label: 'Open days before event' },
];

export const SERIES_IMMEDIATE_HELP =
  'Open immediately opens signups for every upcoming event already generated in the series horizon.';
export const SERIES_POLICY_CHANGE_HELP =
  'Changing this policy recalculates open times for upcoming events in the series.';
export const SERIES_EVENT_POLICY_HELP =
  'Changing the series policy recalculates this open time and overwrites edits made here.';

interface SignupOpenSectionProps<T extends FieldValues & SignupOpenFields> {
  control: Control<T>;
  helpText?: string;
  disabled?: boolean;
}

export function SignupOpenSection<T extends FieldValues & SignupOpenFields>({
  control: parentControl,
  helpText,
  disabled = false,
}: SignupOpenSectionProps<T>) {
  const control = parentControl as unknown as Control<SignupOpenFields>;
  const idPrefix = useId();
  const mode = useWatch({ control, name: 'signup_open_mode' });
  // The days input unmounts outside scheduled mode, taking its error with it,
  // so leaving scheduled restores the last valid hours.
  const { field: hoursField } = useController({
    control,
    name: 'signups_open_hours_before',
  });
  const lastValidHours = useRef(SIGNUP_OPEN_DEFAULTS.signups_open_hours_before);
  useEffect(() => {
    if (isValidHours(hoursField.value))
      lastValidHours.current = hoursField.value;
  }, [hoursField.value]);

  return (
    <div
      className="rounded-md border border-border p-3 space-y-3"
      data-testid="signup-open-section"
    >
      <FormField
        control={control}
        name="signup_open_mode"
        render={({ field }) => (
          <FormItem className="space-y-2">
            <FormLabel className="text-sm font-medium">
              When to open signups
            </FormLabel>
            {helpText && (
              <FormDescription className="text-xs">{helpText}</FormDescription>
            )}
            <FormControl>
              <RadioGroup
                value={field.value}
                onValueChange={(next) => {
                  field.onChange(next);
                  if (next !== 'scheduled' && !isValidHours(hoursField.value)) {
                    hoursField.onChange(lastValidHours.current);
                  }
                }}
                disabled={disabled}
              >
                {SIGNUP_OPEN_OPTIONS.map((option) => (
                  <div key={option.mode} className="flex items-center gap-2">
                    <RadioGroupItem
                      value={option.mode}
                      id={`${idPrefix}-${option.mode}`}
                      data-testid={`signup-open-mode-${option.mode}`}
                    />
                    <Label
                      htmlFor={`${idPrefix}-${option.mode}`}
                      className="text-sm font-normal cursor-pointer"
                    >
                      {option.label}
                    </Label>
                  </div>
                ))}
              </RadioGroup>
            </FormControl>
          </FormItem>
        )}
      />
      {mode === 'scheduled' && (
        <FormField
          control={control}
          name="signups_open_hours_before"
          render={({ field }) => {
            const hours = field.value ?? 0;
            const wholeDays = hours % HOURS_PER_DAY === 0;
            return (
              <FormItem className="ml-6">
                <FormLabel>Days before event</FormLabel>
                <FormControl>
                  <DaysInput field={field} disabled={disabled} />
                </FormControl>
                <FormDescription>
                  {wholeDays
                    ? 'Signups open this many days before the scheduled start'
                    : `Currently ${hours} hours before the scheduled start`}
                </FormDescription>
                <FormMessage />
              </FormItem>
            );
          }}
        />
      )}
    </div>
  );
}

/** Holds its own text so staff can clear the field; commits whole days as hours. */
function DaysInput({
  field,
  disabled,
}: {
  field: ControllerRenderProps<SignupOpenFields, 'signups_open_hours_before'>;
  disabled: boolean;
}) {
  const [text, setText] = useState(() => daysText(field.value));
  const [shownHours, setShownHours] = useState(field.value);
  if (field.value !== shownHours) {
    setShownHours(field.value);
    setText(daysText(field.value));
  }
  return (
    <Input
      type="number"
      min={0}
      max={MAX_DAYS}
      step={1}
      disabled={disabled}
      data-testid="signup-open-days-input"
      name={field.name}
      ref={field.ref}
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        const days = parseInt(e.target.value, 10);
        if (!Number.isNaN(days)) field.onChange(days * HOURS_PER_DAY);
      }}
      onBlur={() => {
        if (Number.isNaN(parseInt(text, 10))) setText(daysText(field.value));
        field.onBlur();
      }}
    />
  );
}
