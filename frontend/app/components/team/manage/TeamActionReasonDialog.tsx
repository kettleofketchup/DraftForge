import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useForm } from 'react-hook-form';

import type { RosterUser } from '~/components/api/teamManagementAPI';
import { ConfirmDialog } from '~/components/ui/dialogs/ConfirmDialog';
import {
  Form,
  FormControl,
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
import { Textarea } from '~/components/ui/textarea';
import { DisplayName } from '~/components/user/avatar';
import { subInSchema, teamActionSchema } from './teamActionSchema';

export interface TeamActionReasonValues {
  reason: string;
  replacing_id?: number | null;
}

export interface TeamActionReasonDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  summary: ReactNode;
  warning?: ReactNode;
  confirmText: string;
  destructive?: boolean;
  defaultReason?: string;
  replacingOptions?: RosterUser[];
  pending: boolean;
  /** Return the request promise: the dialog stays loading until it settles. */
  onSubmit: (values: TeamActionReasonValues) => Promise<unknown>;
}

const NO_ONE = 'none';

function initialValues(
  open: boolean,
  defaultReason: string,
  withReplacing: boolean,
): TeamActionReasonValues {
  const reason = open ? defaultReason : '';
  return withReplacing ? { reason, replacing_id: null } : { reason };
}

export function TeamActionReasonDialog({
  open,
  onOpenChange,
  title,
  summary,
  warning,
  confirmText,
  destructive = false,
  defaultReason = '',
  replacingOptions,
  pending,
  onSubmit,
}: TeamActionReasonDialogProps) {
  const withReplacing = replacingOptions !== undefined;
  const form = useForm<TeamActionReasonValues>({
    resolver: zodResolver(withReplacing ? subInSchema : teamActionSchema),
    mode: 'onChange',
    defaultValues: initialValues(open, defaultReason, withReplacing),
  });
  const inFlight = useRef<Promise<void> | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    form.reset(initialValues(open, defaultReason, withReplacing));
  }, [open, defaultReason, withReplacing, form]);

  // RHF's resolver is async, so isLoading alone lets a second press through.
  const handleConfirm = (): Promise<void> => {
    if (inFlight.current) return inFlight.current;
    if (pending) return Promise.resolve();
    setSubmitting(true);
    const run = (async () => {
      try {
        await form.handleSubmit(async (values) => {
          await onSubmit(values);
        })();
      } finally {
        inFlight.current = null;
        setSubmitting(false);
      }
    })();
    inFlight.current = run;
    return run;
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={summary}
      confirmLabel={confirmText}
      variant={destructive ? 'destructive' : 'default'}
      isLoading={pending || submitting}
      confirmDisabled={!form.formState.isValid}
      onConfirm={handleConfirm}
      confirmTestId="team-action-confirm"
      contentTestId="team-action-dialog"
      bodyContent={
        <Form {...form}>
          <div className="flex flex-col gap-4">
            {warning ? (
              <div className="text-sm" data-testid="team-action-warning">
                {warning}
              </div>
            ) : null}
            {withReplacing ? (
              <FormField
                control={form.control}
                name="replacing_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Replacing</FormLabel>
                    <Select
                      value={field.value == null ? NO_ONE : String(field.value)}
                      onValueChange={(v) =>
                        field.onChange(v === NO_ONE ? null : Number(v))
                      }
                    >
                      <FormControl>
                        <SelectTrigger
                          className="w-full"
                          data-testid="team-action-replacing"
                        >
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={NO_ONE}>No one</SelectItem>
                        {replacingOptions.map((user) => (
                          <SelectItem key={user.pk} value={String(user.pk)}>
                            {DisplayName(user)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-sm text-muted-foreground">
                      Without a replacement the stand-in joins the roster. With
                      one, the replaced player becomes a dropout.
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />
            ) : null}
            <FormField
              control={form.control}
              name="reason"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Reason (recorded in team history)</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      placeholder="Why is this change needed?"
                      data-testid="team-action-reason"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        </Form>
      }
    />
  );
}
