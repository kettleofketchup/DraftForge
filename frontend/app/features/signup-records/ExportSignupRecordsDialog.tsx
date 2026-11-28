import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import {
  downloadSignupRecordsCsv,
  signupRecordsErrorCode,
} from '~/components/api/eventsAPI';
import { SIGNUP_RECORDS_TOO_MANY } from '~/components/events/signupRecordsSchemas';
import { FormDialog } from '~/components/ui/dialogs';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import {
  defaultExportRange,
  exportRangeSchema,
  toExportParams,
  type ExportParams,
  type ExportRange,
} from './exportRange';

const log = getLogger('SignupRecordsExport');

const TOO_MANY_MESSAGE = 'Too many records — choose a shorter range.';
const FALLBACK_MESSAGE = 'Could not export sign-up records.';

export interface ExportSignupRecordsDialogProps {
  orgId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    URL.revokeObjectURL(url);
  }
}

function errorMessage(err: unknown): string {
  if (signupRecordsErrorCode(err) === SIGNUP_RECORDS_TOO_MANY) {
    return TOO_MANY_MESSAGE;
  }
  return extractApiError(err) ?? FALLBACK_MESSAGE;
}

export function ExportSignupRecordsDialog({
  orgId,
  open,
  onOpenChange,
}: ExportSignupRecordsDialogProps) {
  const form = useForm<ExportRange>({
    resolver: zodResolver(exportRangeSchema),
    defaultValues: defaultExportRange(new Date()),
  });

  useEffect(() => {
    if (open) form.reset(defaultExportRange(new Date()));
  }, [open, form]);

  const download = useMutation({
    mutationFn: (params: ExportParams) =>
      downloadSignupRecordsCsv(orgId, params),
  });

  const onSubmit = async (values: ExportRange) => {
    const params = toExportParams(values);
    try {
      const { blob, filename } = await download.mutateAsync(params);
      saveBlob(blob, filename);
      onOpenChange(false);
    } catch (err) {
      log.error('Sign-up records export failed', { orgId, ...params, err });
      toast.error(errorMessage(err));
    }
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Export sign-up records"
      description="Every sign-up for events scheduled in this range, including cancelled and deleted events. Dates are in the organization's timezone."
      submitLabel="Download CSV"
      isSubmitting={download.isPending}
      onSubmit={form.handleSubmit(onSubmit)}
      submitTestId="export-signup-records-submit"
      data-testid="export-signup-records-dialog"
    >
      <Form {...form}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="from"
            render={({ field }) => (
              <FormItem>
                <FormLabel>From</FormLabel>
                <FormControl>
                  <Input
                    type="date"
                    data-testid="export-signup-records-from"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="to"
            render={({ field }) => (
              <FormItem>
                <FormLabel>To</FormLabel>
                <FormControl>
                  <Input
                    type="date"
                    data-testid="export-signup-records-to"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      </Form>
    </FormDialog>
  );
}
