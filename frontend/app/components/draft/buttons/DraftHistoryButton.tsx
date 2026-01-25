import { memo, useCallback, useState } from "react";
import { Badge } from "~/components/ui/badge";
import { SecondaryButton } from "~/components/ui/buttons";
import { History } from "lucide-react";
import type { DraftEvent } from "~/types/draftEvent";
import { DraftEventModal } from "../DraftEventModal";

interface DraftHistoryButtonProps {
  events: DraftEvent[];
  hasNewEvent: boolean;
  onViewed: () => void;
}

export const DraftHistoryButton = memo(function DraftHistoryButton({
  events,
  hasNewEvent,
  onViewed,
}: DraftHistoryButtonProps) {
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
      <SecondaryButton
        data-testid="draft-history-button"
        color="orange"
        onClick={handleClick}
        className="relative"
      >
        <History className="h-4 w-4 md:mr-2" />
        <span className="hidden md:inline">History</span>
        {events.length > 0 && (
          <Badge
            variant={hasNewEvent ? "destructive" : "secondary"}
            className="absolute -top-2 -right-2 h-5 min-w-5 rounded-full text-xs"
          >
            {events.length}
          </Badge>
        )}
      </SecondaryButton>

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
