import { zodResolver } from '@hookform/resolvers/zod';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';
import { DestructiveButton, PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Textarea } from '~/components/ui/textarea';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getLogger } from '~/lib/logger';
import { formatDiscordTimestamps } from './discordPreview';
import { reportPromoError, usePreviewOptions } from './feedback';
import { useDeletePromoTemplate, usePromoTemplates, useSavePromoTemplate } from './queries';
import {
  PLACEHOLDER_KEYS,
  renderTemplate,
  sampleContext,
  type SampleEvent,
  type SampleOrg,
  type SampleSender,
} from './render';
import {
  DISCORD_DM_LIMIT,
  MAX_TEMPLATE_BODY,
  promoTemplateFormSchema,
  type PromoTemplate,
  type PromoTemplateForm,
} from './schemas';

const log = getLogger('TemplatesManager');

const DAY_MS = 24 * 60 * 60 * 1000;

export interface TemplatesManagerProps {
  orgId: number;
  access: OrgFeatureAccess;
  org: SampleOrg;
  sender: SampleSender | null | undefined;
  sampleEvent: SampleEvent | null;
}

function fallbackEvent(): SampleEvent {
  return {
    id: 0,
    name: 'Sample event',
    scheduled_at: new Date(Date.now() + 3 * DAY_MS).toISOString(),
    signups_open_at: null,
  };
}

export function TemplatesManager({
  orgId,
  access,
  org,
  sender,
  sampleEvent,
}: TemplatesManagerProps) {
  const { data: templates = [], isLoading } = usePromoTemplates(orgId, access);
  const remove = useDeletePromoTemplate(orgId, access);
  const [editing, setEditing] = useState<PromoTemplate | 'new' | null>(null);
  const [deleting, setDeleting] = useState<PromoTemplate | null>(null);
  const placeholderEvent = useMemo(fallbackEvent, []);

  if (!access.settled || !access.canManageTemplates) return null;

  const onDelete = async (): Promise<void> => {
    if (!deleting) return;
    try {
      await remove.mutateAsync(deleting.id);
      toast.success('Template deleted');
      setDeleting(null);
    } catch (err: unknown) {
      const message = reportPromoError(log, 'promo_template_delete_failed', err, {
        orgId,
        templateId: deleting.id,
      });
      toast.error(message || 'Could not delete the template');
    }
  };

  return (
    <section
      className="flex flex-col gap-4 rounded-lg border border-primary/40 bg-base-900/40 p-4"
      data-testid="promo-templates-manager"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold">Message templates</h3>
          <p className="text-sm text-muted-foreground">Org staff and above can edit templates.</p>
        </div>
        {editing == null && (
          <SecondaryButton
            type="button"
            onClick={() => setEditing('new')}
            data-testid="promo-template-new-btn"
          >
            <Plus className="h-4 w-4 mr-1.5" />
            New template
          </SecondaryButton>
        )}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading templates...</p>}

      {editing != null && (
        <TemplateEditor
          key={editing === 'new' ? 'new' : editing.id}
          orgId={orgId}
          access={access}
          template={editing === 'new' ? null : editing}
          org={org}
          sender={sender}
          sampleEvent={sampleEvent ?? placeholderEvent}
          onDone={() => setEditing(null)}
        />
      )}

      <ul className="flex flex-col gap-2">
        {templates.map((template) => (
          <li
            key={template.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
            data-testid={`promo-template-row-${template.id}`}
          >
            <div className="min-w-0 flex-1">
              <div className="font-medium">{template.name}</div>
              <div className="truncate text-xs text-muted-foreground">{template.body}</div>
            </div>
            <div className="flex items-center gap-2">
              <SecondaryButton
                type="button"
                size="sm"
                onClick={() => setEditing(template)}
                data-testid={`promo-template-edit-${template.id}`}
              >
                <Pencil className="h-4 w-4 mr-1" />
                Edit
              </SecondaryButton>
              <DestructiveButton
                type="button"
                size="sm"
                onClick={() => setDeleting(template)}
                data-testid={`promo-template-delete-${template.id}`}
              >
                <Trash2 className="h-4 w-4 mr-1" />
                Delete
              </DestructiveButton>
            </div>
          </li>
        ))}
      </ul>

      <ConfirmDialog
        open={deleting != null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title="Delete template?"
        description={`"${deleting?.name ?? ''}" will be removed. Messages already sent keep their text.`}
        confirmLabel="Delete"
        variant="destructive"
        isLoading={remove.isPending}
        onConfirm={onDelete}
      />
    </section>
  );
}

interface TemplateEditorProps {
  orgId: number;
  access: OrgFeatureAccess;
  template: PromoTemplate | null;
  org: SampleOrg;
  sender: SampleSender | null | undefined;
  sampleEvent: SampleEvent;
  onDone: () => void;
}

function TemplateEditor({
  orgId,
  access,
  template,
  org,
  sender,
  sampleEvent,
  onDone,
}: TemplateEditorProps) {
  const save = useSavePromoTemplate(orgId, access);
  const previewOptions = usePreviewOptions();
  const form = useForm<PromoTemplateForm>({
    resolver: zodResolver(promoTemplateFormSchema),
    defaultValues: { name: template?.name ?? '', body: template?.body ?? '' },
  });
  const body = useWatch({ control: form.control, name: 'body' }) ?? '';

  const context = useMemo(
    () => sampleContext(sampleEvent, org, sender),
    [sampleEvent, org, sender],
  );
  const sample = useMemo(() => renderTemplate(body, context), [body, context]);
  const preview = useMemo(
    () => formatDiscordTimestamps(sample.text, previewOptions),
    [sample.text, previewOptions.locale, previewOptions.timeZone],
  );
  const warnings = [...sample.warnings];
  if (sample.text.length > DISCORD_DM_LIMIT) {
    warnings.push(
      `Sample message is ${sample.text.length} characters, over Discord's ${DISCORD_DM_LIMIT} limit`,
    );
  }

  const onSubmit = async (values: PromoTemplateForm): Promise<void> => {
    try {
      const saved = await save.mutateAsync({ id: template?.id ?? null, input: values });
      if (saved.warnings && saved.warnings.length > 0) {
        toast.warning(`Template saved with warnings: ${saved.warnings.join(', ')}`);
      } else {
        toast.success('Template saved');
      }
      onDone();
    } catch (err: unknown) {
      const message = reportPromoError(log, 'promo_template_save_failed', err, {
        orgId,
        templateId: template?.id ?? null,
      });
      toast.error(message || 'Could not save the template');
    }
  };

  return (
    <Form {...form}>
      <form
        className="flex flex-col gap-3 rounded-md border border-border p-3"
        onSubmit={form.handleSubmit(onSubmit)}
        data-testid="promo-template-form"
      >
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Name</FormLabel>
              <FormControl>
                <Input {...field} placeholder="First invite" data-testid="promo-template-name-input" />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="body"
          render={({ field }) => (
            <FormItem>
              <div className="flex items-center justify-between">
                <FormLabel>Body</FormLabel>
                <span className="text-xs tabular-nums text-muted-foreground">
                  {body.length} / {MAX_TEMPLATE_BODY}
                </span>
              </div>
              <FormControl>
                <Textarea
                  {...field}
                  rows={6}
                  className="font-mono text-sm"
                  data-testid="promo-template-body-input"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <p className="text-xs text-muted-foreground" data-testid="promo-template-placeholders">
          Placeholders: {PLACEHOLDER_KEYS.map((key) => `{${key}}`).join(' ')}
        </p>
        {warnings.length > 0 && (
          <ul className="list-disc pl-5 text-xs text-warning" data-testid="promo-template-warnings">
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        )}
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium">Preview</span>
          <div
            className="min-h-16 whitespace-pre-wrap break-words rounded-md border border-border bg-base-800/60 p-3 text-sm"
            data-testid="promo-template-preview"
          >
            {preview}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <PrimaryButton type="submit" disabled={save.isPending} data-testid="promo-template-save-btn">
            {save.isPending ? 'Saving...' : 'Save template'}
          </PrimaryButton>
          <SecondaryButton type="button" onClick={onDone} data-testid="promo-template-cancel-btn">
            Cancel
          </SecondaryButton>
        </div>
      </form>
    </Form>
  );
}
