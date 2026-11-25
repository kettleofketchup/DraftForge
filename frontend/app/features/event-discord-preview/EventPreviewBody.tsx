import type { TFunction } from 'i18next';
import { Info, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  DiscordMessagePreview,
  DiscordScheduledEventCard,
  useOrgDiscordResolver,
  type DiscordResolver,
} from '~/components/discord';
import { Alert, AlertDescription } from '~/components/ui/alert';
import type {
  DiscordPreviewResponse,
  GateCode,
  NoteCode,
  PreviewDestination,
} from './schemas';

type T = TFunction<'discordPreview'>;

function gateText(t: T): Record<GateCode, () => string> {
  return {
    toggle_off: () => t('gate.toggle_off'),
    no_channel: () => t('gate.no_channel'),
    no_signup_channel: () => t('gate.no_signup_channel'),
    state_not_signups_open: () => t('gate.state_not_signups_open'),
    state_not_open_or_roll_call: () => t('gate.state_not_open_or_roll_call'),
    no_signup_post_yet: () => t('gate.no_signup_post_yet'),
    no_discord_server: () => t('gate.no_discord_server'),
    start_in_past: () => t('gate.start_in_past'),
    not_a_series: () => t('gate.not_a_series'),
    no_recipients: () => t('gate.no_recipients'),
    series_paused: () => t('gate.series_paused'),
    series_ended: () => t('gate.series_ended'),
    already_sent: () => t('gate.already_sent'),
    no_scheduled_event_yet: () => t('gate.no_scheduled_event_yet'),
    occurrence_collision: () => t('gate.occurrence_collision'),
  };
}

function noteText(t: T): Record<NoteCode, () => string> {
  return {
    edits_refresh_embed_only: () => t('note.edits_refresh_embed_only'),
    fallback_drops_role_mentions: () => t('note.fallback_drops_role_mentions'),
    signup_link_points_to_post: () => t('note.signup_link_points_to_post'),
    unsaved_links: () => t('note.unsaved_links'),
    sync_overwrites_description: () => t('note.sync_overwrites_description'),
    dm_per_subscriber: () => t('note.dm_per_subscriber'),
    shown_as_posted_when_signups_open: () =>
      t('note.shown_as_posted_when_signups_open'),
    fallback_replaces_notice: () => t('note.fallback_replaces_notice'),
    signup_post_in_signup_channel: () =>
      t('note.signup_post_in_signup_channel'),
    notice_falls_back_if_signup_post_fails: () =>
      t('note.notice_falls_back_if_signup_post_fails'),
    next_event_already_open_not_updated: () =>
      t('note.next_event_already_open_not_updated'),
    existing_event_still_posts: () => t('note.existing_event_still_posts'),
  };
}

function missingText(t: T, field: string): string {
  const known: Record<string, () => string> = {
    name: () => t('missing.name'),
    scheduled_at: () => t('missing.scheduled_at'),
    schedule: () => t('missing.schedule'),
  };
  return known[field]?.() ?? field;
}

function channelLabel(
  t: T,
  id: string | null,
  resolve: DiscordResolver,
): string {
  if (!id) return t('destination.unset');
  const name = resolve.channels?.[id];
  return name ? `#${name}` : t('mention.unknown_channel', { id });
}

function DestinationLine({
  destination,
  resolve,
}: {
  destination: PreviewDestination;
  resolve: DiscordResolver;
}) {
  const { t } = useTranslation('discordPreview');
  const channel = channelLabel(t, destination.channel_id, resolve);
  const lines: string[] = [];
  switch (destination.type) {
    case 'channel':
      lines.push(t('destination.channel', { channel }));
      break;
    case 'forum_thread':
      lines.push(
        t('destination.forum_thread', {
          channel,
          thread: destination.thread_name ?? '',
        }),
      );
      break;
    case 'dm':
      lines.push(t('destination.dm'));
      break;
    case 'reply':
      lines.push(
        destination.channel_id
          ? t('destination.reply', { channel })
          : t('destination.reply_unknown'),
      );
      break;
    case 'scheduled_event':
      lines.push(t('destination.scheduled_event'));
      break;
  }
  if (destination.fallback_channel_id)
    lines.push(
      t('destination.fallback', {
        channel: channelLabel(t, destination.fallback_channel_id, resolve),
      }),
    );
  return (
    <div data-testid="discord-preview-destination" className="text-sm">
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </div>
  );
}

export function EventPreviewBody({
  data,
  organizationId,
}: {
  data: DiscordPreviewResponse;
  organizationId: number;
}) {
  const { t } = useTranslation('discordPreview');
  const orgResolve = useOrgDiscordResolver(organizationId, { enabled: true });
  const resolve: DiscordResolver = {
    ...orgResolve,
    users: data.mentions.users,
  };

  if (data.status === 'unavailable') {
    return (
      <p data-testid="discord-preview-unavailable" className="text-sm">
        {t('status.unavailable')}
      </p>
    );
  }

  if (data.status === 'needs_input') {
    return (
      <p data-testid="discord-preview-needs-input" className="text-sm">
        {t('status.needs_input', {
          fields: data.missing.map((f) => missingText(t, f)).join(', '),
        })}
      </p>
    );
  }

  const gates = gateText(t);
  const notes = noteText(t);
  const seriesGate = data.note_args.series_gate;
  const seriesGateText =
    seriesGate && seriesGate in gates ? gates[seriesGate as GateCode]() : null;
  const header = data.note_args.header;
  const author = { name: t('message.bot_name'), bot: true };
  const replyTo =
    data.destination?.type === 'reply' ? t('message.reply_label') : undefined;

  return (
    <div className="space-y-3">
      {!data.saved ? (
        <Alert data-testid="discord-preview-unsaved">
          <Info />
          <AlertDescription>{t('banner.unsaved')}</AlertDescription>
        </Alert>
      ) : null}
      {data.destination ? (
        <DestinationLine destination={data.destination} resolve={resolve} />
      ) : null}
      <div data-testid="discord-preview-gate" className="text-sm">
        {data.gate.would_send ? (
          <p>{t('gate.would_send')}</p>
        ) : (
          data.gate.reasons.map((code) => (
            <p
              key={code}
              data-gate={code}
              className="flex items-start gap-2 text-warning"
            >
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
              <span>{gates[code]()}</span>
            </p>
          ))
        )}
      </div>
      {header && data.messages.length === 0 ? (
        <div
          data-testid="discord-preview-start-mention-header"
          className="space-y-1 rounded-md border border-border bg-base-800 p-3 text-sm text-muted-foreground"
        >
          <p className="text-xs font-semibold">
            {t('start_mention.header_label')}
          </p>
          <p>{header}</p>
        </div>
      ) : null}
      {data.scheduled_event ? (
        <DiscordScheduledEventCard
          event={data.scheduled_event}
          resolve={resolve}
        />
      ) : null}
      {data.messages.length > 0 ? (
        <DiscordMessagePreview
          messages={data.messages}
          author={author}
          resolve={resolve}
          replyTo={replyTo}
        />
      ) : null}
      {data.variants.map((variant) => (
        <section
          key={variant.code}
          data-testid={`discord-preview-variant-${variant.code}`}
          className="space-y-2"
        >
          <p className="text-sm font-semibold">{t('variant.current_post')}</p>
          <DiscordMessagePreview
            messages={variant.messages}
            author={author}
            resolve={resolve}
          />
        </section>
      ))}
      {data.notes.length > 0 ? (
        <ul
          data-testid="discord-preview-notes"
          className="space-y-1 text-sm text-muted-foreground"
        >
          {data.notes.map((code) => (
            <li key={code} data-note={code}>
              {notes[code]()}
              {code === 'existing_event_still_posts' && seriesGateText
                ? ` ${seriesGateText}`
                : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
