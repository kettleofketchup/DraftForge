import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useFieldArray, useWatch, type UseFormReturn } from 'react-hook-form';
import { toast } from 'sonner';

import { SecondaryButton } from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { Switch } from '~/components/ui/switch';
import {
  MAX_ACTIVE_TRAITS,
  TRAIT_LABEL_MAX_LENGTH,
  refusalCode,
  refusalMessage,
  refusalStatus,
  useDeleteTrait,
  type TraitForm,
} from '~/features/leadership';
import { slugifyTraitKey } from '~/features/leadership/traitForm';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getLogger } from '~/lib/logger';

const log = getLogger('LeadershipTraitEditor');

type TraitRow = TraitForm['traits'][number];

const ICON_BUTTON = 'size-11 sm:size-9';

/** Replaces the baseline and the current rows in one step, so `isDirty` compares the two. */
function rebase(
  form: UseFormReturn<TraitForm>,
  baseline: TraitRow[],
  current: TraitRow[],
): void {
  form.reset({ traits: baseline });
  form.reset({ traits: current }, { keepDefaultValues: true });
}

export function LeadershipTraitEditor({
  form,
  orgId,
  access,
}: {
  form: UseFormReturn<TraitForm>;
  orgId: number;
  access: OrgFeatureAccess;
}) {
  const { fields, append, swap } = useFieldArray({
    control: form.control,
    name: 'traits',
  });
  const rows = useWatch({ control: form.control, name: 'traits' }) ?? [];
  const deleteTrait = useDeleteTrait(orgId);
  const [newLabel, setNewLabel] = useState('');
  const [confirmKey, setConfirmKey] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});

  const isDirty = form.formState.isDirty;
  useEffect(() => {
    if (!isDirty) setRowErrors({});
  }, [isDirty]);

  const clearRowError = (key: string) =>
    setRowErrors((prev) => {
      if (!(key in prev)) return prev;
      const { [key]: _cleared, ...rest } = prev;
      return rest;
    });

  const activeCount = rows.filter((t) => t.active).length;
  const traitErrors = form.formState.errors.traits;
  const rootError = traitErrors?.root?.message ?? traitErrors?.message;
  const confirmRow = rows.find((t) => t.key === confirmKey);

  const baseline = (): TraitRow[] =>
    (form.formState.defaultValues?.traits ?? []) as TraitRow[];

  const dropRow = (key: string, fromBaseline: boolean) => {
    const current = form.getValues('traits').filter((t) => t.key !== key);
    const base = fromBaseline
      ? baseline().filter((t) => t.key !== key)
      : baseline();
    rebase(form, base, current);
  };

  const addTrait = () => {
    const name = newLabel.trim();
    if (!name) return;
    append({
      key: slugifyTraitKey(name, new Set(rows.map((t) => t.key))),
      label: name,
      active: activeCount < MAX_ACTIVE_TRAITS,
      saved: false,
    });
    setNewLabel('');
  };

  const onDelete = (row: TraitRow) => {
    if (row.saved) setConfirmKey(row.key);
    else dropRow(row.key, false);
  };

  const confirmDelete = async () => {
    const row = confirmRow;
    if (!row) return;
    try {
      await deleteTrait.mutateAsync(row.key);
      dropRow(row.key, true);
      toast.success(`Deleted ${row.label}`);
    } catch (err) {
      const message = refusalMessage(err, 'trait');
      log.warn('Trait delete refused', {
        orgId,
        key: row.key,
        code: refusalCode(err),
      });
      if (refusalStatus(err) === 404) {
        dropRow(row.key, true);
        toast.error(message);
        return;
      }
      if (refusalCode(err) !== 'trait_in_use') {
        toast.error(message);
        return;
      }
      const index = form
        .getValues('traits')
        .findIndex((t) => t.key === row.key);
      if (index >= 0) {
        form.setValue(`traits.${index}.active`, false, { shouldDirty: true });
      }
      setRowErrors((prev) => ({ ...prev, [row.key]: message }));
    }
  };

  return (
    <Form {...form}>
      <fieldset
        className="flex min-w-0 flex-col gap-3"
        data-testid="leadership-trait-editor"
      >
        <legend className="mb-2 text-sm font-semibold">Traits</legend>
        <p className="text-sm text-muted-foreground">
          Teammates score each active trait from 1 to 5. A trait that already
          has scores can only be deactivated.
        </p>
        <p
          className="text-sm font-medium"
          data-testid="leadership-traits-count"
        >
          {activeCount} of {MAX_ACTIVE_TRAITS} active
        </p>
        <ol className="flex flex-col gap-3">
          {fields.map((item, index) => {
            const row = rows[index] ?? item;
            const name = row.label || 'trait';
            const rowError = !row.active ? rowErrors[row.key] : undefined;
            const testId = `leadership-trait-${row.key}`;
            return (
              <li
                key={item.id}
                data-testid={testId}
                className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-start"
              >
                <FormField
                  control={form.control}
                  name={`traits.${index}.label`}
                  render={({ field }) => (
                    <FormItem className="min-w-0 flex-1">
                      <FormLabel className="sr-only">
                        Trait {index + 1} name
                      </FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          maxLength={TRAIT_LABEL_MAX_LENGTH}
                          placeholder="Trait name"
                          data-testid={`${testId}-label`}
                        />
                      </FormControl>
                      <FormMessage />
                      {traitErrors?.[index]?.key?.message && (
                        <p className="text-sm text-destructive">
                          {traitErrors[index]?.key?.message}
                        </p>
                      )}
                      {rowError && (
                        <p
                          className="text-sm break-words text-muted-foreground"
                          data-testid={`${testId}-error`}
                        >
                          {rowError}
                        </p>
                      )}
                    </FormItem>
                  )}
                />
                <div className="flex flex-wrap items-center gap-2">
                  <FormField
                    control={form.control}
                    name={`traits.${index}.active`}
                    render={({ field }) => (
                      <FormItem className="flex min-h-11 items-center gap-2 space-y-0 sm:min-h-9">
                        <FormControl>
                          <Switch
                            checked={field.value}
                            onCheckedChange={(checked) => {
                              clearRowError(row.key);
                              field.onChange(checked);
                            }}
                            aria-label={`${name} active`}
                            data-testid={`${testId}-active`}
                          />
                        </FormControl>
                        <FormLabel className="text-sm">Active</FormLabel>
                      </FormItem>
                    )}
                  />
                  <SecondaryButton
                    type="button"
                    size="icon"
                    className={ICON_BUTTON}
                    aria-label={`Move ${name} up`}
                    data-testid={`${testId}-up`}
                    disabled={index === 0}
                    onClick={() => swap(index, index - 1)}
                  >
                    <ArrowUp />
                  </SecondaryButton>
                  <SecondaryButton
                    type="button"
                    size="icon"
                    className={ICON_BUTTON}
                    aria-label={`Move ${name} down`}
                    data-testid={`${testId}-down`}
                    disabled={index === fields.length - 1}
                    onClick={() => swap(index, index + 1)}
                  >
                    <ArrowDown />
                  </SecondaryButton>
                  <SecondaryButton
                    type="button"
                    size="icon"
                    className={ICON_BUTTON}
                    aria-label={`Delete ${name}`}
                    data-testid={`${testId}-delete`}
                    disabled={deleteTrait.isPending}
                    onClick={() => onDelete(row)}
                  >
                    <Trash2 />
                  </SecondaryButton>
                </div>
              </li>
            );
          })}
        </ol>
        {rootError && (
          <p
            className="text-sm text-destructive"
            role="alert"
            data-testid="leadership-traits-error"
          >
            {rootError}
          </p>
        )}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <Label htmlFor="leadership-trait-new-label">New trait</Label>
            <Input
              id="leadership-trait-new-label"
              value={newLabel}
              maxLength={TRAIT_LABEL_MAX_LENGTH}
              placeholder="Shot calling"
              data-testid="leadership-trait-new-label"
              onChange={(e) => setNewLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key !== 'Enter') return;
                e.preventDefault();
                addTrait();
              }}
            />
          </div>
          <SecondaryButton
            type="button"
            className="min-h-11 sm:min-h-9"
            data-testid="leadership-trait-add"
            disabled={newLabel.trim() === ''}
            onClick={addTrait}
          >
            <Plus data-icon="inline-start" />
            Add trait
          </SecondaryButton>
        </div>
      </fieldset>
      <ConfirmDialog
        open={confirmKey !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmKey(null);
        }}
        title={`Delete ${confirmRow?.label || 'this trait'}?`}
        description="Teammates stop scoring it. A trait that already has scores can't be deleted; it is deactivated instead."
        confirmLabel="Delete trait"
        variant="destructive"
        isLoading={deleteTrait.isPending}
        onConfirm={confirmDelete}
        confirmTestId="leadership-trait-delete-confirm"
        cancelTestId="leadership-trait-delete-cancel"
      />
    </Form>
  );
}
