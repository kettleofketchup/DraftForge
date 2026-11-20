import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { Link } from 'react-router';

import {
  overrideReasonFormSchema,
  type OverrideReasonFormValues,
  type OverrideRequired,
} from '~/components/api/overridesAPI';
import type { OrganizationType } from '~/components/organization/schemas';
import { Badge } from '~/components/ui/badge';
import { CancelButton, SubmitButton } from '~/components/ui/buttons';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Textarea } from '~/components/ui/textarea';
import { useIsOrganizationAdmin } from '~/hooks/usePermissions';
import { cn } from '~/lib/utils';

export interface OverrideWarningDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  override: OverrideRequired | null;
  onConfirm: (reason: string) => Promise<void> | void;
  organization?: OrganizationType | null;
  submitting?: boolean;
  reasonError?: string | null;
  defaultReason?: string;
  minReasonLength?: number;
  reasonLabel?: string;
}

export function orgStaffPlacementPath(organizationId: number): string {
  return `/organizations/${organizationId}?tab=settings`;
}

export function OverrideWarningDialog({
  open,
  onOpenChange,
  override,
  onConfirm,
  organization,
  submitting = false,
  reasonError = null,
  defaultReason = '',
  minReasonLength = 1,
  reasonLabel = 'Reason',
}: OverrideWarningDialogProps) {
  const isOrgAdmin = useIsOrganizationAdmin(organization);
  const schema = useMemo(
    () => overrideReasonFormSchema(minReasonLength),
    [minReasonLength],
  );
  const form = useForm<OverrideReasonFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { reason: open ? defaultReason : '' },
  });

  useEffect(() => {
    form.reset({ reason: open ? defaultReason : '' });
  }, [open, defaultReason, form]);

  const blocked = override?.blocked ?? false;
  const violations = override?.violations ?? [];

  const handleSubmit = async (values: OverrideReasonFormValues) => {
    await onConfirm(values.reason);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-lg max-h-[90vh] overflow-y-auto"
        data-testid="override-warning-dialog"
      >
        <DialogHeader>
          <DialogTitle>
            {blocked ? 'Override blocked' : 'Override rules?'}
          </DialogTitle>
          <DialogDescription>
            {blocked
              ? "This action breaks rules your organization's staff override policy blocks."
              : 'This action breaks the rules below. Confirm with a reason to continue.'}
          </DialogDescription>
        </DialogHeader>

        <ul className="flex flex-col gap-2" data-testid="override-violations">
          {violations.map((violation, i) => (
            <li
              key={`${i}-${violation.code}`}
              data-testid={`override-violation-${violation.code}-${i}`}
              data-blocking={violation.blocking}
              className={cn(
                'rounded-md border p-3',
                violation.blocking
                  ? 'border-destructive bg-destructive/10'
                  : 'border-border bg-base-800/40',
              )}
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold">{violation.rule}</span>
                {violation.blocking && (
                  <Badge
                    variant="destructive"
                    data-testid="override-blocking-badge"
                  >
                    Blocked
                  </Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                {violation.message}
              </p>
            </li>
          ))}
        </ul>

        {blocked ? (
          <>
            <p className="text-sm" data-testid="override-blocked-policy">
              {isOrgAdmin && organization?.pk != null ? (
                <>
                  Change the policy in{' '}
                  <Link
                    to={orgStaffPlacementPath(organization.pk)}
                    className="text-interactive underline"
                    data-testid="override-settings-link"
                  >
                    organization settings, Staff placement
                  </Link>
                  .
                </>
              ) : (
                'Ask an org admin to change the staff override policy.'
              )}
            </p>
            <DialogFooter>
              <CancelButton onClick={() => onOpenChange(false)}>
                Close
              </CancelButton>
            </DialogFooter>
          </>
        ) : (
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(handleSubmit)}
              className="flex flex-col gap-4"
            >
              <FormField
                control={form.control}
                name="reason"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{reasonLabel}</FormLabel>
                    <FormControl>
                      <Textarea
                        {...field}
                        placeholder="Why is this override needed?"
                        data-testid="override-reason"
                      />
                    </FormControl>
                    <FormMessage />
                    {reasonError && (
                      <p
                        role="alert"
                        className="text-sm text-destructive"
                        data-testid="override-reason-error"
                      >
                        {reasonError}
                      </p>
                    )}
                  </FormItem>
                )}
              />
              <DialogFooter>
                <CancelButton
                  type="button"
                  onClick={() => onOpenChange(false)}
                />
                <SubmitButton
                  loading={submitting}
                  loadingText="Confirming..."
                  data-testid="override-confirm"
                >
                  Confirm override
                </SubmitButton>
              </DialogFooter>
            </form>
          </Form>
        )}
      </DialogContent>
    </Dialog>
  );
}
