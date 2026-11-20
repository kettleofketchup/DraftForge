import { Activity } from 'lucide-react';
import { TournamentEditForm } from '~/components/tournament/create/editForm';
import type {
  TournamentClassType,
  TournamentType,
} from '~/components/tournament/types';
import { DiscordActivityLog } from './DiscordActivityLog';

interface Props {
  tournament: TournamentType;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canEdit: boolean;
}

export function TournamentSettingsModal({
  tournament,
  open,
  onOpenChange,
  canEdit,
}: Props) {
  return (
    <TournamentEditForm
      tourn={tournament as TournamentClassType}
      open={open}
      onOpenChange={onOpenChange}
      title={`Tournament Settings — ${tournament.name}`}
      onSuccess={() => onOpenChange(false)}
      canEdit={canEdit}
      extraSections={
        tournament.pk
          ? [
              {
                value: 'activity',
                label: 'Discord Activity',
                icon: Activity,
                lazy: true,
                keywords: ['log', 'messages', 'history'],
                content: <DiscordActivityLog tournamentId={tournament.pk} />,
              },
            ]
          : []
      }
    />
  );
}
