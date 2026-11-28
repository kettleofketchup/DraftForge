import type { TFunction } from 'i18next';
import { useFormContext } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import {
  DiscordPreviewButton,
  type DiscordPreviewRenderControls,
} from '~/components/discord';
import { openSignupsFromForm } from '~/components/events/createEventPayload';
import {
  useEventFormNavigation,
  type EventFormNavigation,
} from '~/components/events/form/EventFormNavigation';
import { useUserStore } from '~/store/userStore';
import { previewEventDiscordMessage } from './api';
import {
  toApiContext,
  valuesModeFor,
  type DiscordPreviewContext,
} from './context';
import { EventPreviewBody, type MissingFieldAction } from './EventPreviewBody';
import { eventDiscordPreviewKeys } from './queryKeys';
import type { PreviewKind } from './schemas';
import { toPreviewValues } from './toPreviewValues';

export function kindTitle(
  t: TFunction<'discordPreview'>,
): Record<PreviewKind, () => string> {
  return {
    scheduled_event: () => t('kind.scheduled_event'),
    scheduled_event_sync: () => t('kind.scheduled_event_sync'),
    signup_reminder: () => t('kind.signup_reminder'),
    profile_reminder: () => t('kind.profile_reminder'),
    attendance_reminder: () => t('kind.attendance_reminder'),
    start_mention: () => t('kind.start_mention'),
    signup_post: () => t('kind.signup_post'),
    announcement_notice: () => t('kind.announcement_notice'),
    new_event_post: () => t('kind.new_event_post'),
  };
}

const MISSING_FIELD_DESTINATIONS: ReadonlyMap<string, string> = new Map([
  ['name', 'name'],
  ['scheduled_at', 'scheduled_at'],
  ['schedule', 'frequency'],
]);

function missingFieldActions(
  navigation: EventFormNavigation,
  controls: DiscordPreviewRenderControls,
): MissingFieldAction {
  return (code) => {
    const destination = MISSING_FIELD_DESTINATIONS.get(code);
    if (destination === undefined) return undefined;
    return () =>
      controls.closeAndThen(() => navigation.navigateToField(destination));
  };
}

export function EventDiscordPreviewButton({
  kind,
  organizationId,
  context,
}: {
  kind: PreviewKind;
  organizationId: number;
  context?: DiscordPreviewContext;
}) {
  const { t } = useTranslation('discordPreview');
  const form = useFormContext<Record<string, unknown>>();
  const viewerId = useUserStore((s) => s.currentUser?.pk);
  const navigation = useEventFormNavigation();
  const title = kindTitle(t)[kind]();
  const testId = `discord-preview-${kind}`;

  if (!context) {
    return (
      <DiscordPreviewButton
        queryKey={[]}
        title={title}
        data-testid={testId}
        body={
          <p data-testid="discord-preview-unavailable" className="text-sm">
            {t('status.unavailable')}
          </p>
        }
      />
    );
  }

  const fetchPreview = () => {
    const values = form.getValues();
    const { mode, creating } = valuesModeFor(context);
    return previewEventDiscordMessage({
      kind,
      context: toApiContext(context),
      values: toPreviewValues(values, mode, { creating }),
      open_signups: openSignupsFromForm(
        values as Parameters<typeof openSignupsFromForm>[0],
      ),
    });
  };

  return (
    <DiscordPreviewButton
      queryKey={eventDiscordPreviewKeys.preview(kind, context, viewerId)}
      title={title}
      data-testid={testId}
      fetchPreview={fetchPreview}
      render={(data, controls) => (
        <EventPreviewBody
          data={data}
          organizationId={organizationId}
          missingFieldAction={
            navigation ? missingFieldActions(navigation, controls) : undefined
          }
        />
      )}
    />
  );
}
