import { ExternalLink } from 'lucide-react';

import { PrimaryButton } from '~/components/ui/buttons';

import { isAllowedExternalLink, type BotAccessSnapshot } from '../schemas';
import { botCount } from './BaseBotAccessHelp';

export const DOTA2_NOT_LINKED_MESSAGE =
  'This league has no Steam league ID. Add one in Edit League to check bot access.';

export function Dota2BotAccessHelp({
  snapshot,
}: {
  snapshot: BotAccessSnapshot;
}) {
  const adminsUrl = snapshot.league_link?.url;
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p data-testid="bot-access-summary" className="font-medium">
        {botCount(snapshot)} can host lobbies in Steam league{' '}
        {snapshot.external_league_id}.
      </p>
      <p className="text-muted-foreground">
        To add a bot: in the League Administrators section of the league&apos;s
        admins page, add the bot by its Steam profile link, then press Refresh
        access. If Steam asks you to log in first, reopen the league from your
        league list afterwards. Valve can take a while to report a new admin.
      </p>
      {adminsUrl && isAllowedExternalLink(adminsUrl) ? (
        <PrimaryButton
          asChild
          size="sm"
          className="min-h-11 self-start sm:min-h-8"
        >
          <a
            href={adminsUrl}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="bot-access-admins-link"
          >
            Open league admins page
            <ExternalLink className="size-4" aria-hidden="true" />
          </a>
        </PrimaryButton>
      ) : null}
    </div>
  );
}
