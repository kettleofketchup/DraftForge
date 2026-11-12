import { InfoDialog } from "~/components/ui/dialogs";
import { UserAvatar } from "~/components/user/UserAvatar";
import type {
  CaptainPresencePayload,
  CaptainRef,
  DraftEvent,
  PickSkippedPayload,
  PlayerPickedPayload,
} from "~/types/draftEvent";
import { getEventIcon, getEventMessage } from "./eventMessages";
import { formatDistanceToNow } from "date-fns";

interface DraftEventModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  events: DraftEvent[];
}

interface EventAvatars {
  captain?: string | null;
  picked?: string | null;
}

const CAPTAIN_AVATAR_EVENTS = new Set<DraftEvent["event_type"]>([
  "captain_assigned",
  "round_started",
  "captain_ready",
  "captain_unready",
  "captain_connected",
  "captain_disconnected",
  "draft_paused",
  "pick_timed_out",
  "pick_skip_unavailable",
]);

function getEventAvatars(event: DraftEvent): EventAvatars {
  const avatars: EventAvatars = {};

  if (event.event_type === "player_picked") {
    const payload = event.payload as PlayerPickedPayload;
    avatars.captain = payload.captain_avatar_url;
    avatars.picked = payload.picked_avatar_url;
  } else if (event.event_type === "pick_skipped") {
    const payload = event.payload as PickSkippedPayload;
    avatars.captain = payload.skipped_captain_avatar_url;
    avatars.picked = payload.next_captain_avatar_url;
  } else if (CAPTAIN_AVATAR_EVENTS.has(event.event_type)) {
    avatars.captain = (event.payload as CaptainRef | CaptainPresencePayload).captain_avatar_url;
  }

  return avatars;
}

function EventAvatarDisplay({ avatars }: { avatars: EventAvatars }) {
  if (!avatars.captain && !avatars.picked) return null;

  return (
    <div className="flex items-center gap-1 flex-shrink-0">
      {avatars.captain && (
        <UserAvatar src={avatars.captain} size="sm" alt="Captain" />
      )}
      {avatars.picked && (
        <>
          <span className="text-muted-foreground text-xs">→</span>
          <UserAvatar src={avatars.picked} size="sm" alt="Picked" />
        </>
      )}
    </div>
  );
}

export function DraftEventModal({ open, onOpenChange, events }: DraftEventModalProps) {
  return (
    <InfoDialog
      open={open}
      onOpenChange={onOpenChange}
      title={<span data-testid="draft-event-history-title">Draft Event History</span>}
      size="md"
      showClose={false}
    >
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
                data-testid={`draft-event-row-${event.event_type}`}
                className="flex items-start gap-3 p-2 rounded-lg bg-muted/50"
              >
                <span className="text-lg">{getEventIcon(event.event_type)}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <EventAvatarDisplay avatars={avatars} />
                    <p className="text-sm font-medium" data-testid="draft-event-text">
                      {getEventMessage(event)}
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
    </InfoDialog>
  );
}
