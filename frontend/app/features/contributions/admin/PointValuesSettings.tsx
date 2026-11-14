import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';
import { Badge } from '~/components/ui/badge';
import { SecondaryButton } from '~/components/ui/buttons';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { describePointValue } from '../pointValues';
import { usePointValues, useSetPointValue } from '../queries';
import { KIND_LABELS, pointValueInputSchema, type PointValueRow } from '../schemas';
import { RescoreDialog, type RescoreChoice } from './RescoreDialog';

const log = getLogger('PointValuesSettings');

const PointValueFormSchema = z.object({ points: pointValueInputSchema });
type PointValueFormValues = z.infer<typeof PointValueFormSchema>;

interface PendingChange {
  row: PointValueRow;
  points: number | null;
}

export interface PointValuesSettingsProps {
  orgId: number;
  access: OrgFeatureAccess;
}

export function PointValuesSettings({ orgId, access }: PointValuesSettingsProps) {
  const { data: rows, isLoading, isError, error } = usePointValues(orgId, access);
  const mutation = useSetPointValue(orgId, access);
  const [pending, setPending] = useState<PendingChange | null>(null);

  const confirm = async (choice: RescoreChoice): Promise<void> => {
    if (!pending) return;
    const { row, points } = pending;
    const label = KIND_LABELS[row.kind];
    try {
      const result = await mutation.mutateAsync({
        kind: row.kind,
        update: { points, ...choice },
      });
      toast.success(
        choice.apply_to_past
          ? `${label} set to ${result.new}; ${result.changed} entries rescored`
          : `${label} set to ${result.new}`,
      );
    } catch (err) {
      log.warn('Failed to save point value', { orgId, kind: row.kind, err });
      toast.error(extractApiError(err) ?? `Failed to save ${label}`);
    }
  };

  return (
    <section className="flex flex-col gap-3" data-testid="point-values-settings">
      <h4 className="font-semibold">Point values</h4>
      {isLoading && <p className="text-sm text-muted-foreground">Loading point values...</p>}
      {isError && (
        <p className="text-sm text-destructive" data-testid="point-values-error">
          {extractApiError(error) ?? 'Could not load point values.'}
        </p>
      )}
      <div className="flex flex-col gap-2">
        {rows?.map((row) => (
          <PointValueRowForm
            key={`${row.kind}:${row.points}:${row.is_default}`}
            row={row}
            disabled={mutation.isPending}
            onSave={(points) => setPending({ row, points })}
          />
        ))}
      </div>
      {pending && (
        <RescoreDialog
          key={`${pending.row.kind}:${pending.points ?? 'default'}`}
          open
          onOpenChange={(open) => {
            if (!open) setPending(null);
          }}
          kindLabel={KIND_LABELS[pending.row.kind]}
          from={pending.row.points}
          to={pending.points ?? pending.row.default}
          isReset={pending.points === null}
          isPending={mutation.isPending}
          onConfirm={confirm}
        />
      )}
    </section>
  );
}

interface PointValueRowFormProps {
  row: PointValueRow;
  disabled: boolean;
  onSave: (points: number | null) => void;
}

function PointValueRowForm({ row, disabled, onSave }: PointValueRowFormProps) {
  const { label, canReset } = describePointValue(row);
  const form = useForm<PointValueFormValues>({
    resolver: zodResolver(PointValueFormSchema),
    defaultValues: { points: row.points },
  });
  const value = form.watch('points');

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit((values) => onSave(values.points))}
        className="flex flex-wrap items-start gap-3 rounded-md border border-border p-3"
        data-testid={`point-value-row-${row.kind}`}
      >
        <FormField
          control={form.control}
          name="points"
          render={({ field }) => (
            <FormItem className="flex min-w-48 flex-1 flex-col gap-1">
              <div className="flex items-center gap-2">
                <FormLabel>{KIND_LABELS[row.kind]}</FormLabel>
                <Badge
                  variant={canReset ? 'default' : 'outline'}
                  data-testid={`point-value-badge-${row.kind}`}
                >
                  {label}
                </Badge>
                <span className="text-xs text-muted-foreground">default {row.default}</span>
              </div>
              <FormControl>
                <Input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  step={1}
                  className="w-28"
                  name={field.name}
                  ref={field.ref}
                  onBlur={field.onBlur}
                  value={Number.isNaN(field.value) ? '' : field.value}
                  onChange={(e) =>
                    field.onChange(e.target.value === '' ? Number.NaN : Number(e.target.value))
                  }
                  disabled={disabled}
                  data-testid={`point-value-${row.kind}`}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <div className="flex gap-2 pt-6">
          <SecondaryButton
            type="submit"
            size="sm"
            disabled={disabled || value === row.points}
            data-testid={`point-value-save-${row.kind}`}
          >
            Save
          </SecondaryButton>
          {canReset && (
            <SecondaryButton
              type="button"
              size="sm"
              disabled={disabled}
              onClick={() => onSave(null)}
              data-testid={`point-value-reset-${row.kind}`}
            >
              Reset to default
            </SecondaryButton>
          )}
        </div>
      </form>
    </Form>
  );
}
