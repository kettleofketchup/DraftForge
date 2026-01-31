import { memo, useCallback, useState } from "react";
import { HistoryButton } from "~/components/ui/buttons";
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
      <HistoryButton
        data-testid="draft-history-button"
        onClick={handleClick}
        eventCount={events.length}
        hasNewEvent={hasNewEvent}
        tooltipText="Draft Events"
      />

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
