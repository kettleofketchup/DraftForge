import { Check } from 'lucide-react';
import { relativeFromIso, usePreviewOptions } from './feedback';
import type { ExternalContact, LastMessaged } from './schemas';

export interface ContactRecordedStatusProps {
  externalContact: ExternalContact | null;
  localLastMessaged: LastMessaged | null;
  /** The candidate row's test id suffix; also scopes the element ids. */
  testId: string;
}

/** Element id of the imported-contact note, for `aria-describedby`. */
export function externalContactId(testId: string): string {
  return `promo-external-contact-${testId}-note`;
}

function absoluteTime(iso: string, locale: string, timeZone: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone,
    }).format(date);
  } catch {
    return date.toISOString();
  }
}

/**
 * A candidate's recorded contact history for this event, one line per source.
 *
 * The local line is a DraftForge send. The external line is an imported record
 * that someone contacted this player: it is shown as a read-only checked tick,
 * it does not prove delivery, and DraftForge cannot undo it.
 */
export function ContactRecordedStatus({
  externalContact,
  localLastMessaged,
  testId,
}: ContactRecordedStatusProps) {
  const previewOptions = usePreviewOptions();
  if (!externalContact && !localLastMessaged) return null;
  const noteId = externalContactId(testId);
  return (
    <>
      {localLastMessaged && (
        <span data-testid={`promo-last-messaged-${testId}`}>
          Messaged by {localLastMessaged.by ?? 'someone'},{' '}
          {relativeFromIso(localLastMessaged.sent_at, previewOptions)}
        </span>
      )}
      {externalContact && (
        <span
          className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-0.5"
          data-testid={`promo-external-contact-${testId}`}
        >
          <span
            role="checkbox"
            aria-checked="true"
            aria-readonly="true"
            aria-label="Contact recorded externally"
            aria-describedby={noteId}
            tabIndex={0}
            className="inline-flex size-4 shrink-0 items-center justify-center rounded-sm border border-success bg-success/20 text-success focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            data-testid={`promo-external-tick-${testId}`}
          >
            <Check className="size-3" aria-hidden="true" />
          </span>
          <span className="font-medium text-foreground">
            Contact recorded externally
          </span>
          <span id={noteId}>
            <time
              dateTime={externalContact.recorded_at}
              title={absoluteTime(
                externalContact.recorded_at,
                previewOptions.locale,
                previewOptions.timeZone,
              )}
            >
              {relativeFromIso(externalContact.recorded_at, previewOptions)}
            </time>
            {' · '}
            {externalContact.delivery_verified
              ? 'Delivery verified'
              : 'Delivery not verified'}
          </span>
        </span>
      )}
    </>
  );
}
