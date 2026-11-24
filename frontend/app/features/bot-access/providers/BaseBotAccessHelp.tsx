import type { BotAccessSnapshot } from '../schemas';

export const BASE_NOT_LINKED_MESSAGE =
  "This league isn't linked to an external league. Add one in Edit League to check bot access.";

export function botCount(snapshot: BotAccessSnapshot): string {
  const held = snapshot.held_count;
  if (snapshot.roster === 'holders')
    return held === 1 ? '1 bot' : `${held} bots`;
  return `${held} of ${snapshot.bots.length} bots`;
}

export function BaseBotAccessHelp({
  snapshot,
}: {
  snapshot: BotAccessSnapshot;
}) {
  const verb =
    snapshot.roster === 'holders' && snapshot.held_count === 1 ? 'has' : 'have';
  return (
    <p data-testid="bot-access-summary" className="text-sm font-medium">
      {botCount(snapshot)} {verb} access to this league.
    </p>
  );
}
