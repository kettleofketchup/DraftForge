import { Settings } from 'lucide-react';
import { DiscordIcon } from '~/components/events/DiscordConfigSection';
import { TournamentEditForm } from '~/components/tournament/create/editForm';
import type {
  TournamentClassType,
  TournamentType,
} from '~/components/tournament/types';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-screen max-w-none sm:max-w-none h-screen max-h-none rounded-none border-0 overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Tournament Settings — {tournament.name}</DialogTitle>
        </DialogHeader>

        <Tabs
          defaultValue="settings"
          className="flex-1 overflow-hidden flex flex-col"
        >
          <TabsList className="w-full">
            <TabsTrigger value="settings" className="flex-1">
              <Settings className="h-4 w-4 mr-2" />
              Settings
            </TabsTrigger>
            <TabsTrigger value="discord" className="flex-1">
              <DiscordIcon className="h-4 w-4 mr-2" />
              Discord Activity
            </TabsTrigger>
          </TabsList>

          <TabsContent
            value="settings"
            className="mt-4 flex min-h-0 flex-1 flex-col"
          >
            <TournamentEditForm
              tourn={tournament as TournamentClassType}
              onSuccess={() => onOpenChange(false)}
              canEdit={canEdit}
            />
          </TabsContent>

          <TabsContent value="discord" className="flex-1 overflow-auto mt-4">
            {tournament.pk && (
              <DiscordActivityLog tournamentId={tournament.pk} />
            )}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
