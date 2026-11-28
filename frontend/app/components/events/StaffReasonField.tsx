import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect } from 'react';
import { useForm, type UseFormReturn } from 'react-hook-form';
import {
  OVERRIDE_REASON_MAX_LENGTH,
  staffReasonFormSchema,
  type OverrideReasonFormValues,
} from '~/components/api/overridesAPI';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';

export function useStaffReasonForm(
  required: boolean,
  resetKey: unknown,
  open: boolean,
): UseFormReturn<OverrideReasonFormValues> {
  const form = useForm<OverrideReasonFormValues>({
    resolver: zodResolver(staffReasonFormSchema(required)),
    mode: 'onChange',
    defaultValues: { reason: '' },
  });
  const { reset } = form;
  useEffect(() => {
    reset({ reason: '' });
  }, [open, resetKey, reset]);
  return form;
}

export function StaffReasonField({
  form,
  required,
  onSubmit,
  autoFocus = required,
}: {
  form: UseFormReturn<OverrideReasonFormValues>;
  required: boolean;
  onSubmit: () => void | Promise<void>;
  autoFocus?: boolean;
}) {
  return (
    <FormField
      control={form.control}
      name="reason"
      render={({ field }) => (
        <FormItem>
          <FormLabel>
            {required
              ? 'Reason (recorded in signup history)'
              : 'Reason (optional)'}
          </FormLabel>
          <FormControl>
            <Input
              {...field}
              autoFocus={autoFocus}
              data-testid="staff-reason-input"
              onKeyDown={(event) => {
                if (event.key !== 'Enter' || event.nativeEvent.isComposing)
                  return;
                event.preventDefault();
                event.stopPropagation();
                void form.handleSubmit(() => onSubmit())();
              }}
            />
          </FormControl>
          <p className="text-sm text-muted-foreground">
            {field.value.length}/{OVERRIDE_REASON_MAX_LENGTH}
          </p>
          <FormMessage data-testid="staff-reason-error" />
        </FormItem>
      )}
    />
  );
}
