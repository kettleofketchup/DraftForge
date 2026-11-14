import { zodResolver } from '@hookform/resolvers/zod';
import { Copy, ExternalLink, Undo2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';
import {
  BrandSelect,
  BrandSelectContent,
  BrandSelectItem,
  BrandSelectTrigger,
  SelectValue,
} from '~/components/ui/brand-select';
import { PrimaryButton, SecondaryButton } from '~/components/ui/buttons';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Textarea } from '~/components/ui/textarea';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { formatDiscordTimestamps } from './discordPreview';
import { reportPromoError, usePreviewOptions } from './feedback';
import { useRenderPromo, useSendPromo, useUndoPromoSend } from './queries';
import {
  DISCORD_DM_LIMIT,
  promoSendSchema,
  type CandidateRow,
  type PromoEvent,
  type PromoSendForm,
  type PromoSendResult,
  type PromoTemplate,
} from './schemas';

const log = getLogger('ComposePanel');

export interface ComposePanelProps {
  orgId: number;
  access: OrgFeatureAccess;
  event: PromoEvent;
  candidate: CandidateRow;
  templates: PromoTemplate[];
  onSent?: (send: PromoSendResult | null) => void;
}

export function candidateName(
  row: Pick<CandidateRow, 'nickname' | 'username'>,
): string {
  return row.nickname || row.username;
}

export function ComposePanel({
  orgId,
  access,
  event,
  candidate,
  templates,
  onSent,
}: ComposePanelProps) {
  const [templateId, setTemplateId] = useState<number | null>(
    templates[0]?.id ?? null,
  );
  const [sent, setSent] = useState<PromoSendResult | null>(null);
  const previewOptions = usePreviewOptions();

  useEffect(() => {
    if (templateId == null || !templates.some((t) => t.id === templateId)) {
      setTemplateId(templates[0]?.id ?? null);
    }
  }, [templates, templateId]);

  const rendered = useRenderPromo(
    orgId,
    access,
    event.id,
    templateId,
    candidate.user_pk,
  );
  const send = useSendPromo(orgId, access, event.id);
  const undo = useUndoPromoSend(orgId, access);

  const form = useForm<PromoSendForm>({
    resolver: zodResolver(promoSendSchema),
    defaultValues: { text: '' },
    mode: 'onChange',
  });
  const renderedText = rendered.data?.text;
  useEffect(() => {
    form.reset({ text: renderedText ?? '' });
  }, [renderedText, templateId, candidate.user_pk, form]);

  const text = useWatch({ control: form.control, name: 'text' }) ?? '';
  const preview = useMemo(
    () => formatDiscordTimestamps(text, previewOptions),
    [text, previewOptions],
  );
  const overLimit = text.length > DISCORD_DM_LIMIT;
  const canSubmit =
    promoSendSchema.safeParse({ text }).success &&
    !send.isPending &&
    sent == null;

  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success('Message copied');
    } catch {
      toast.error('Could not copy the message');
    }
  };

  const onSubmit = (values: PromoSendForm): void => {
    send.mutate(
      {
        template_id: templateId,
        recipient_id: candidate.user_pk,
        text: values.text,
      },
      {
        onSuccess: (result) => {
          setSent(result);
          onSent?.(result);
          toast.success(`Marked as sent to ${candidateName(candidate)}`);
        },
        onError: (err) => {
          const message = reportPromoError(log, 'promo_send_failed', err, {
            orgId,
            eventId: event.id,
            recipientId: candidate.user_pk,
          });
          toast.error(message || 'Could not record the message');
        },
      },
    );
  };

  const onUndo = (sendId: number): void => {
    undo.mutate(sendId, {
      onSuccess: () => {
        setSent(null);
        onSent?.(null);
        toast.success('Send undone');
      },
      onError: (err) => {
        const message = reportPromoError(log, 'promo_undo_failed', err, {
          orgId,
          sendId,
        });
        toast.error(message || 'Could not undo the send');
      },
    });
  };

  useEffect(() => {
    if (rendered.error) {
      reportPromoError(log, 'promo_render_failed', rendered.error, {
        orgId,
        eventId: event.id,
        recipientId: candidate.user_pk,
      });
    }
  }, [rendered.error, orgId, event.id, candidate.user_pk]);
  const renderError = rendered.isError
    ? (extractApiError(rendered.error) ?? 'Could not fill in this template.')
    : null;

  return (
    <section
      className="flex flex-col gap-4 rounded-lg border border-border bg-base-900/40 p-4"
      data-testid="promo-compose-panel"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">Message {candidateName(candidate)}</h3>
        {candidate.discordId && (
          <a
            href={`https://discord.com/users/${candidate.discordId}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
            data-testid="promo-discord-profile-link"
          >
            Open Discord profile
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
      </div>

      {templates.length === 0 ? (
        <p
          className="text-sm text-muted-foreground"
          data-testid="promo-no-templates"
        >
          No templates yet. Ask an org staff member to add one.
        </p>
      ) : (
        <BrandSelect
          value={templateId != null ? String(templateId) : undefined}
          onValueChange={(value) => setTemplateId(Number(value))}
        >
          <BrandSelectTrigger
            className="w-full sm:w-72"
            aria-label="Template"
            data-testid="promo-template-select"
          >
            <SelectValue placeholder="Pick a template" />
          </BrandSelectTrigger>
          <BrandSelectContent>
            {templates.map((template) => (
              <BrandSelectItem
                key={template.id}
                value={String(template.id)}
                data-testid={`promo-template-option-${template.id}`}
              >
                {template.name}
              </BrandSelectItem>
            ))}
          </BrandSelectContent>
        </BrandSelect>
      )}

      {rendered.isLoading && (
        <p className="text-sm text-muted-foreground">
          Filling in the template...
        </p>
      )}
      {renderError != null && (
        <p
          className="text-sm text-destructive"
          data-testid="promo-render-error"
        >
          {renderError}
        </p>
      )}

      <Form {...form}>
        <form
          className="flex flex-col gap-3"
          onSubmit={form.handleSubmit(onSubmit)}
        >
          <FormField
            control={form.control}
            name="text"
            render={({ field }) => (
              <FormItem>
                <div className="flex items-center justify-between">
                  <FormLabel>Message</FormLabel>
                  <span
                    className={cn(
                      'text-xs tabular-nums',
                      overLimit
                        ? 'text-warning font-semibold'
                        : 'text-muted-foreground',
                    )}
                    data-testid="promo-char-count"
                  >
                    {text.length} / {DISCORD_DM_LIMIT}
                  </span>
                </div>
                <FormControl>
                  <Textarea
                    {...field}
                    rows={8}
                    className="font-mono text-sm"
                    data-testid="promo-message-text"
                  />
                </FormControl>
                {overLimit && (
                  <p className="text-xs text-warning">
                    Over Discord's 2000-character limit for senders without
                    Nitro.
                  </p>
                )}
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium">
              How it will look in Discord
            </span>
            <div
              className="min-h-16 whitespace-pre-wrap break-words rounded-md border border-border bg-base-800/60 p-3 text-sm"
              data-testid="promo-discord-preview"
            >
              {preview}
            </div>
          </div>

          {rendered.data && !rendered.data.will_earn && (
            <p
              className="text-sm text-muted-foreground"
              data-testid="promo-no-points-note"
            >
              This message won't earn points: this player was already messaged
              for this event, or your role doesn't earn points.
            </p>
          )}
          {rendered.data?.will_earn && access.canViewContributions && (
            <p
              className="text-sm text-muted-foreground"
              data-testid="promo-earn-points-note"
            >
              Marking this sent earns you contribution points.
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <SecondaryButton
              type="button"
              onClick={copy}
              disabled={text.length === 0}
              data-testid="promo-copy-btn"
            >
              <Copy className="h-4 w-4 mr-1.5" />
              Copy
            </SecondaryButton>
            <PrimaryButton
              type="submit"
              disabled={!canSubmit}
              data-testid="promo-mark-sent-btn"
            >
              {send.isPending ? 'Saving...' : 'Mark sent'}
            </PrimaryButton>
          </div>
        </form>
      </Form>

      {sent && (
        <div
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-base-800/60 p-3 text-sm"
          data-testid="promo-sent-banner"
        >
          <span>
            Sent to {candidateName(candidate)}.
            {access.canViewContributions && sent.points_awarded != null && (
              <span
                className="ml-1 text-primary"
                data-testid="promo-earned-hint"
              >
                You earned {sent.points_awarded} points.
              </span>
            )}
          </span>
          <SecondaryButton
            type="button"
            size="sm"
            onClick={() => onUndo(sent.id)}
            disabled={undo.isPending}
            data-testid={`promo-undo-${sent.id}`}
          >
            <Undo2 className="h-4 w-4 mr-1" />
            Undo
          </SecondaryButton>
        </div>
      )}
    </section>
  );
}
