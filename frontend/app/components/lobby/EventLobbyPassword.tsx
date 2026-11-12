import { useTranslation } from 'react-i18next';
import { KeyRound } from 'lucide-react';
import { Card, CardContent, CardHeader } from '~/components/ui/card';
import { useEventLobbyPassword } from '~/hooks/useLobbyPassword';
import { CopyPasswordButton } from './CopyPasswordButton';

interface EventLobbyPasswordProps {
  eventId: number;
  /** The event hosts lobbies (dota_lobby_mode is not off). */
  lobbiesEnabled: boolean;
  /** Only signed-in users can be registered or staff. */
  signedIn: boolean;
}

/**
 * The event's lobby password, ahead of time, for its staff and registered
 * players. The endpoint answers 404 to everyone else, so nothing shows.
 */
export function EventLobbyPassword({ eventId, lobbiesEnabled, signedIn }: EventLobbyPasswordProps) {
  const { t } = useTranslation('lobby');
  const { data } = useEventLobbyPassword(eventId, lobbiesEnabled && signedIn);
  if (!lobbiesEnabled || !data?.password) return null;

  return (
    <Card data-testid="event-lobby-password">
      <CardHeader>
        <h3 className="font-semibold flex items-center gap-2">
          <KeyRound className="size-4" />
          {t('password.event.title')}
        </h3>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-center gap-2">
          <code
            className="rounded bg-muted px-2 py-1 text-sm"
            data-testid="event-lobby-password-value"
          >
            {data.password}
          </code>
          <CopyPasswordButton password={data.password} data-testid="event-lobby-password-copy" />
        </div>
        <p className="text-xs text-muted-foreground">{t('password.event.description')}</p>
      </CardContent>
    </Card>
  );
}
