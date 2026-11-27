import { CalendarDays, MapPin } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '~/lib/utils';
import { DiscordMarkdown } from './DiscordMarkdown';
import {
  formatDiscordTimestamp,
  usePreviewOptions,
  type DiscordPreviewOptions,
} from './timestamps';
import type { DiscordResolver, ScheduledEventPreview } from './types';

function unixFromIso(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : Math.floor(ms / 1000);
}

export function DiscordScheduledEventCard({
  event,
  resolve,
  options,
  className,
}: {
  event: ScheduledEventPreview;
  resolve?: DiscordResolver;
  options?: DiscordPreviewOptions;
  className?: string;
}) {
  const { t } = useTranslation('discordPreview');
  const viewerOptions = usePreviewOptions();
  const opts = options ?? viewerOptions;
  const start = unixFromIso(event.scheduled_start_time);
  const end = unixFromIso(event.scheduled_end_time);
  const location = event.entity_metadata.location;

  return (
    <article
      data-testid="discord-scheduled-event"
      className={cn(
        'space-y-2 rounded-md border border-border bg-base-900 p-4 text-sm text-foreground',
        className,
      )}
    >
      {start !== null ? (
        <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
          <CalendarDays aria-hidden className="size-4" />
          <span className="sr-only">{t('scheduled_event.starts')}</span>
          <span>{formatDiscordTimestamp(start, 'F', opts)}</span>
          {end !== null ? (
            <>
              <span aria-hidden>–</span>
              <span className="sr-only">{t('scheduled_event.ends')}</span>
              <span>{formatDiscordTimestamp(end, 'F', opts)}</span>
            </>
          ) : null}
        </div>
      ) : null}
      <div className="text-base font-semibold">{event.name}</div>
      {event.description ? (
        <DiscordMarkdown
          text={event.description}
          resolve={resolve}
          options={opts}
        />
      ) : null}
      {location ? (
        <div className="flex items-center gap-2 text-muted-foreground">
          <MapPin aria-hidden className="size-4 shrink-0" />
          <span className="sr-only">{t('scheduled_event.location')}</span>
          <span className="break-all">{location}</span>
        </div>
      ) : null}
    </article>
  );
}
