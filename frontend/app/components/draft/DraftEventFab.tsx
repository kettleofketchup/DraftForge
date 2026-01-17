import { memo, useCallback, useState } from "react";
import { Button } from "~/components/ui/button";
import { Badge } from "~/components/ui/badge";
import { History } from "lucide-react";
import { cn } from "~/lib/utils";
import type { DraftEvent } from "~/types/draftEvent";
import { DraftEventModal } from "./DraftEventModal";

interface DraftEventFabProps {
  events: DraftEvent[];
  hasNewEvent: boolean;
  onViewed: () => void;
  isConnected: boolean;
}

export const DraftEventFab = memo(function DraftEventFab({
  events,
  hasNewEvent,
  onViewed,
  isConnected,
}: DraftEventFabProps) {
  const [modalOpen, setModalOpen] = useState(false);

  const handleOpenChange = useCallback((open: boolean) => {
    setModalOpen(open);
    if (open) {
      onViewed();
    }
  }, [onViewed]);

  const handleClick = useCallback(() => {
    setModalOpen(true);
    onViewed();
  }, [onViewed]);

  return (
    <>
      <Button
        data-testid="draft-event-fab"
        variant="default"
        size="icon"
        className={cn(
          "fixed bottom-6 right-6 h-14 w-14 rounded-full shadow-lg z-50",
          hasNewEvent && "animate-pulse"
        )}
        onClick={handleClick}
      >
        <History className="h-6 w-6" />
        {events.length > 0 && (
          <Badge
            variant={hasNewEvent ? "destructive" : "secondary"}
            className="absolute -top-1 -right-1 h-6 min-w-6 rounded-full"
          >
            {events.length}
          </Badge>
        )}
        {!isConnected && (
          <span className="absolute bottom-0 right-0 h-3 w-3 rounded-full bg-yellow-500 border-2 border-background" />
        )}
      </Button>

      {/* Only render modal when open to avoid Dialog interference with hover */}
      {modalOpen && (
        <DraftEventModal
          open={modalOpen}
          onOpenChange={handleOpenChange}
          events={events}
        />
      )}
    </>
  );
});
