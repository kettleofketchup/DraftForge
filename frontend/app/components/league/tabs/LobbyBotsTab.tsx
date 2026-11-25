import { BotAccessPanel } from '~/features/bot-access';

interface Props {
  leaguePk: number;
  enabled: boolean;
}

export const LobbyBotsTab: React.FC<Props> = ({ leaguePk, enabled }) => (
  <BotAccessPanel leagueId={leaguePk} enabled={enabled} />
);
