import { zodResolver } from '@hookform/resolvers/zod';
import { Copy, ExternalLink, Undo2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';
import { DiscordMessagePreview } from '~/components/discord';
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
import { DisplayName } from '~/components/user/avatar';
import { UserAvatar } from '~/components/user/UserAvatar';
import type { OrgFeatureAccess } from '~/features/org-features';
import { extractApiError } from '~/lib/apiError';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { useUserStore } from '~/store/userStore';
import { reportPromoError } from './feedback';
import type { ComposeMode } from './promotionColumns';
import { useRenderPromo, useSendPromo, useUndoPromoSend } from './queries';
import {
  DISCORD_DM_LIMIT,
  promoSendSchema,
  type LinkedCandidate,
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
  candidate: LinkedCandidate;
  templates: PromoTemplate[];
  onSent?: (send: PromoSendResult | null) => void;
  /** "record" logs a DM the sender already sent; both only record, never send. */
  mode?: ComposeMode;
  /** Inside a dialog that already titles the recipient: no frame or heading. */
  embedded?: boolean;
}

const MODE_NOTE: Record<ComposeMode, string> = {
  message:
    "DraftForge doesn't send DMs. Copy the message, send it to them on Discord, then mark it sent.",
  record:
    'Record a DM you already sent on Discord. Pick the template you used and make the text match what you sent. Nothing is sent from DraftForge.',
};

export function ComposePanel({
  orgId,
  access,
  event,
  candidate,
  templates,
  onSent,
  mode = 'message',
  embedded = false,
}: ComposePanelProps) {
  const [templateId, setTemplateId] = useState<number | null>(
    templates[0]?.id ?? null,
  );
  const [sent, setSent] = useState<PromoSendResult | null>(null);
  const currentUser = useUserStore((state) => state.currentUser);

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
  const previewMessages = useMemo(() => [{ content: text }], [text]);
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
          toast.success(`Marked as sent to ${DisplayName(candidate)}`);
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
      className={cn(
        'flex flex-col gap-4',
        !embedded && 'rounded-lg border border-border bg-base-900/40 p-4',
      )}
      data-testid="promo-compose-panel"
      data-mode={mode}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        {embedded ? (
          <span className="text-sm text-muted-foreground">
            {/* eslint-disable-next-line draftforge/use-display-name -- the Discord @handle to DM */}
            {candidate.discordUsername ? `@${candidate.discordUsername}` : null}
          </span>
        ) : (
          <h3 className="font-semibold">Message {DisplayName(candidate)}</h3>
        )}
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

      <p
        className="text-sm text-muted-foreground"
        data-testid={`promo-${mode}-note`}
      >
        {MODE_NOTE[mode]}
      </p>

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
            <div data-testid="promo-discord-preview">
              <DiscordMessagePreview
                className="min-h-16"
                messages={previewMessages}
                author={
                  currentUser?.pk
                    ? {
                        name: DisplayName(currentUser),
                        avatar: (
                          <UserAvatar
                            user={currentUser}
                            size="lg"
                            data-testid="promo-sender-avatar"
                          />
                        ),
                        bot: false,
                      }
                    : undefined
                }
              />
            </div>
          </div>

          {rendered.data &&
            !rendered.data.will_earn &&
            access.canViewContributions && (
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
              {send.isPending
                ? 'Saving...'
                : mode === 'record'
                  ? 'Record as sent'
                  : 'Mark sent'}
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
            Sent to {DisplayName(candidate)}.
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
