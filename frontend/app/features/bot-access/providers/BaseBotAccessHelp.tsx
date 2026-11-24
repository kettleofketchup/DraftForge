import type { BotAccessSnapshot } from '../schemas';

export const BASE_NOT_LINKED_MESSAGE =
  "This league isn't linked to an external league. Add one in Edit League to check bot access.";

export function BaseBotAccessHelp({
  snapshot,
}: {
  snapshot: BotAccessSnapshot;
}) {
  return (
    <p data-testid="bot-access-summary" className="text-sm font-medium">
      {snapshot.held_count} of {snapshot.bots.length} bots have access to this
      league.
    </p>
  );
}
