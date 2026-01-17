import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import type { DraftEvent, WebSocketDraftState, WebSocketMessage } from "~/types/draftEvent";
import { getLogger } from "~/lib/logger";

const log = getLogger("useDraftWebSocket");

interface UseDraftWebSocketOptions {
  draftId: number | null;
  onEvent?: (event: DraftEvent) => void;
  /** Called when draft state is received via WebSocket - use this to update state directly */
  onDraftStateUpdate?: (draftState: WebSocketDraftState | unknown) => void;
  /** Fallback called when no draft state is included (for backwards compatibility) */
  onRefreshNeeded?: () => void;
}

interface UseDraftWebSocketReturn {
  events: DraftEvent[];
  isConnected: boolean;
  connectionError: string | null;
  hasNewEvent: boolean;
  clearNewEventFlag: () => void;
}

const SIGNIFICANT_EVENTS: DraftEvent["event_type"][] = [
  "draft_started",
  "draft_completed",
  "player_picked",
  "tie_roll",
];

function getEventMessage(event: DraftEvent): string {
  switch (event.event_type) {
    case "draft_started":
      return "Draft has started!";
    case "draft_completed":
      return "Draft completed!";
    case "player_picked": {
      const payload = event.payload as { captain_name: string; picked_name: string; pick_number: number };
      return `${payload.captain_name} picked ${payload.picked_name} (Pick ${payload.pick_number})`;
    }
    case "tie_roll": {
      const payload = event.payload as { winner_name: string; roll_rounds: { captain_id: number; roll: number }[][] };
      const lastRound = payload.roll_rounds[payload.roll_rounds.length - 1];
      const rolls = lastRound.map((r) => r.roll).join(" vs ");
      return `Tie resolved! ${payload.winner_name} wins (${rolls})`;
    }
    case "captain_assigned": {
      const payload = event.payload as { captain_name: string };
      return `${payload.captain_name} is picking next`;
    }
    case "pick_undone": {
      const payload = event.payload as { undone_player_name: string; pick_number: number };
      return `Pick ${payload.pick_number} undone (${payload.undone_player_name})`;
    }
    default:
      return "Draft event occurred";
  }
}

export function useDraftWebSocket({
  draftId,
  onEvent,
  onDraftStateUpdate,
  onRefreshNeeded,
}: UseDraftWebSocketOptions): UseDraftWebSocketReturn {
  const [events, setEvents] = useState<DraftEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [hasNewEvent, setHasNewEvent] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Store callbacks in refs to avoid triggering reconnects when they change
  const onEventRef = useRef(onEvent);
  const onDraftStateUpdateRef = useRef(onDraftStateUpdate);
  const onRefreshNeededRef = useRef(onRefreshNeeded);

  // Keep refs up to date without triggering reconnects
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    onDraftStateUpdateRef.current = onDraftStateUpdate;
  }, [onDraftStateUpdate]);

  useEffect(() => {
    onRefreshNeededRef.current = onRefreshNeeded;
  }, [onRefreshNeeded]);

  const clearNewEventFlag = useCallback(() => {
    setHasNewEvent(false);
  }, []);

  const connect = useCallback(() => {
    if (!draftId) return;

    // Don't reconnect if already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      log.debug("WebSocket already connected, skipping reconnect");
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/draft/${draftId}/`;

    log.debug(`Connecting to WebSocket: ${wsUrl}`);

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      log.debug("WebSocket connected");
      setIsConnected(true);
      setConnectionError(null);
    };

    ws.onmessage = (messageEvent) => {
      try {
        const data: WebSocketMessage = JSON.parse(messageEvent.data);
        log.debug("WebSocket message:", data);

        if (data.type === "initial_events" && data.events) {
          setEvents(data.events);
        } else if (data.type === "draft_event" && data.event) {
          const newEvent = data.event;

          // Add to events list (newest first)
          setEvents((prev) => [newEvent, ...prev]);
          setHasNewEvent(true);

          // Show toast for significant events
          if (SIGNIFICANT_EVENTS.includes(newEvent.event_type)) {
            toast(getEventMessage(newEvent));
          }

          // Update draft state directly if included (avoids API calls)
          if (data.draft_state && onDraftStateUpdateRef.current) {
            log.debug("Updating draft state from WebSocket:", data.draft_state);
            onDraftStateUpdateRef.current(data.draft_state);
          } else {
            // Fallback to refresh callback if no draft state included
            onRefreshNeededRef.current?.();
          }

          onEventRef.current?.(newEvent);
        }
      } catch (err) {
        log.error("Failed to parse WebSocket message:", err);
      }
    };

    ws.onclose = (closeEvent) => {
      log.debug("WebSocket closed:", closeEvent.code, closeEvent.reason);
      setIsConnected(false);

      // Attempt reconnect after 3 seconds (only for unexpected closes)
      if (closeEvent.code !== 1000) {
        reconnectTimeoutRef.current = setTimeout(() => {
          log.debug("Attempting reconnect...");
          connect();
        }, 3000);
      }
    };

    ws.onerror = (error) => {
      log.error("WebSocket error:", error);
      setConnectionError("Connection error");
    };
  }, [draftId]); // Only depend on draftId - callbacks are accessed via refs

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close(1000, "Component unmounting");
      }
    };
  }, [connect]);

  return {
    events,
    isConnected,
    connectionError,
    hasNewEvent,
    clearNewEventFlag,
  };
}
