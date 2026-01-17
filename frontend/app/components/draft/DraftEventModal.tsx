import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import { ScrollArea } from "~/components/ui/scroll-area";
import type { DraftEvent, PlayerPickedPayload, CaptainAssignedPayload } from "~/types/draftEvent";
import { formatDistanceToNow } from "date-fns";

interface DraftEventModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  events: DraftEvent[];
}

function getEventIcon(eventType: DraftEvent["event_type"]): string {
  switch (eventType) {
    case "draft_started":
      return "▶️";
    case "draft_completed":
      return "🏁";
    case "player_picked":
      return "🎯";
    case "tie_roll":
      return "🎲";
    case "captain_assigned":
      return "👑";
    case "pick_undone":
      return "↩️";
    default:
      return "📋";
  }
}

interface EventAvatars {
  captain?: string | null;
  picked?: string | null;
}

function getEventAvatars(event: DraftEvent): EventAvatars {
  const avatars: EventAvatars = {};

  if (event.event_type === "player_picked") {
    const payload = event.payload as PlayerPickedPayload;
    avatars.captain = payload.captain_avatar_url;
    avatars.picked = payload.picked_avatar_url;
  } else if (event.event_type === "captain_assigned") {
    const payload = event.payload as CaptainAssignedPayload;
    avatars.captain = payload.captain_avatar_url;
  }

  return avatars;
}

function getEventDescription(event: DraftEvent): string {
  switch (event.event_type) {
    case "draft_started":
      return "Draft started";
    case "draft_completed":
      return "Draft completed";
    case "player_picked": {
      const payload = event.payload as PlayerPickedPayload;
      return `${payload.captain_name} picked ${payload.picked_name} (Pick ${payload.pick_number})`;
    }
    case "tie_roll": {
      const payload = event.payload as {
        tied_captains: { name: string }[];
        roll_rounds: { captain_id: number; roll: number }[][];
        winner_name: string;
      };
      const names = payload.tied_captains.map((c) => c.name).join(" vs ");
      const lastRound = payload.roll_rounds[payload.roll_rounds.length - 1];
      const rolls = lastRound.map((r) => `${r.roll}`).join(" vs ");
      return `Tie! ${names} rolled ${rolls} → ${payload.winner_name} wins`;
    }
    case "captain_assigned": {
      const payload = event.payload as CaptainAssignedPayload;
      return `${payload.captain_name} is picking next`;
    }
    case "pick_undone": {
      const payload = event.payload as { undone_player_name: string; pick_number: number };
      return `Pick ${payload.pick_number} undone (${payload.undone_player_name})`;
    }
    default:
      return "Unknown event";
  }
}

function EventAvatarDisplay({ avatars }: { avatars: EventAvatars }) {
  if (!avatars.captain && !avatars.picked) return null;

  return (
    <div className="flex items-center gap-1 flex-shrink-0">
      {avatars.captain && (
        <img
          src={avatars.captain}
          alt="Captain"
          className="w-6 h-6 rounded-full"
        />
      )}
      {avatars.picked && (
        <>
          <span className="text-muted-foreground text-xs">→</span>
          <img
            src={avatars.picked}
            alt="Picked"
            className="w-6 h-6 rounded-full"
          />
        </>
      )}
    </div>
  );
}

export function DraftEventModal({ open, onOpenChange, events }: DraftEventModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Draft Event History</DialogTitle>
        </DialogHeader>
        <ScrollArea className="h-[400px] pr-4">
          {events.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              No events yet
            </p>
          ) : (
            <div className="space-y-3">
              {events.map((event) => {
                const avatars = getEventAvatars(event);
                return (
                  <div
                    key={event.pk}
                    className="flex items-start gap-3 p-2 rounded-lg bg-muted/50"
                  >
                    <span className="text-lg">{getEventIcon(event.event_type)}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <EventAvatarDisplay avatars={avatars} />
                        <p className="text-sm font-medium">
                          {getEventDescription(event)}
                        </p>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {formatDistanceToNow(new Date(event.created_at), {
                          addSuffix: true,
                        })}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
