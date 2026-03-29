import { Settings } from 'lucide-react';
import { useState } from 'react';
import { Button } from '~/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '~/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';
import type { TournamentClassType } from '~/components/tournament/types';
import { TournamentEditForm } from '~/components/tournament/create/editForm';
import { DiscordActivityLog } from './DiscordActivityLog';
import { DiscordIcon } from '~/components/events/DiscordConfigSection';
import type { TournamentType } from '~/components/tournament/types';

interface Props {
  tournament: TournamentType;
}

export function TournamentSettingsModal({ tournament }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <DialogTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                data-testid="tournament-settings-button"
              >
                <Settings className="h-4 w-4" />
              </Button>
            </DialogTrigger>
          </TooltipTrigger>
          <TooltipContent>Tournament Settings</TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Tournament Settings — {tournament.name}</DialogTitle>
        </DialogHeader>

        <Tabs defaultValue="settings" className="flex-1 overflow-hidden flex flex-col">
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

          <TabsContent value="settings" className="flex-1 overflow-auto mt-4">
            <TournamentEditForm
              tourn={tournament as TournamentClassType}
              onSuccess={() => setOpen(false)}
            />
          </TabsContent>

          <TabsContent value="discord" className="flex-1 overflow-auto mt-4">
            {tournament.pk && <DiscordActivityLog tournamentId={tournament.pk} />}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
