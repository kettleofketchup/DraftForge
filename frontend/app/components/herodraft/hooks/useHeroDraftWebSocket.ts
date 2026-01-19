import { useCallback, useEffect, useRef, useState } from "react";
import { getLogger } from "~/lib/logger";
import type { HeroDraft, HeroDraftTick } from "../types";

const log = getLogger("useHeroDraftWebSocket");

interface HeroDraftWebSocketMessage {
  type: "initial_state" | "herodraft_event" | "herodraft_tick";
  draft_state?: HeroDraft;
  event_type?: string;
  draft_team?: number | null;
  // Tick fields
  current_round?: number;
  active_team_id?: number | null;
  grace_time_remaining_ms?: number;
  team_a_reserve_ms?: number;
  team_b_reserve_ms?: number;
}

interface UseHeroDraftWebSocketOptions {
  draftId: number | null;
  onStateUpdate?: (draft: HeroDraft) => void;
  onTick?: (tick: HeroDraftTick) => void;
  onEvent?: (eventType: string, draftTeam: number | null) => void;
}

interface UseHeroDraftWebSocketReturn {
  isConnected: boolean;
  connectionError: string | null;
}

export function useHeroDraftWebSocket({
  draftId,
  onStateUpdate,
  onTick,
  onEvent,
}: UseHeroDraftWebSocketOptions): UseHeroDraftWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Store callbacks in refs to avoid triggering reconnects when they change
  const onStateUpdateRef = useRef(onStateUpdate);
  const onTickRef = useRef(onTick);
  const onEventRef = useRef(onEvent);

  // Keep refs up to date without triggering reconnects
  useEffect(() => {
    onStateUpdateRef.current = onStateUpdate;
  }, [onStateUpdate]);

  useEffect(() => {
    onTickRef.current = onTick;
  }, [onTick]);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  const connect = useCallback(() => {
    if (!draftId) return;

    // Don't reconnect if already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      log.debug("WebSocket already connected, skipping reconnect");
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/herodraft/${draftId}/`;

    log.debug(`Connecting to HeroDraft WebSocket: ${wsUrl}`);

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      log.debug("HeroDraft WebSocket connected");
      setIsConnected(true);
      setConnectionError(null);
    };

    ws.onmessage = (messageEvent) => {
      try {
        const data: HeroDraftWebSocketMessage = JSON.parse(messageEvent.data);
        log.debug("HeroDraft WebSocket message:", data);

        switch (data.type) {
          case "initial_state":
            if (data.draft_state && onStateUpdateRef.current) {
              onStateUpdateRef.current(data.draft_state);
            }
            break;

          case "herodraft_event":
            if (data.draft_state && onStateUpdateRef.current) {
              onStateUpdateRef.current(data.draft_state);
            }
            if (data.event_type && onEventRef.current) {
              onEventRef.current(data.event_type, data.draft_team ?? null);
            }
            break;

          case "herodraft_tick":
            if (onTickRef.current && data.current_round !== undefined) {
              onTickRef.current({
                type: "herodraft_tick",
                current_round: data.current_round,
                active_team_id: data.active_team_id ?? null,
                grace_time_remaining_ms: data.grace_time_remaining_ms ?? 0,
                team_a_reserve_ms: data.team_a_reserve_ms ?? 0,
                team_b_reserve_ms: data.team_b_reserve_ms ?? 0,
                draft_state: data.draft_state?.state ?? "",
              });
            }
            break;
        }
      } catch (err) {
        log.error("Failed to parse HeroDraft WebSocket message:", err);
      }
    };

    ws.onclose = (closeEvent) => {
      log.debug("HeroDraft WebSocket closed:", closeEvent.code, closeEvent.reason);
      setIsConnected(false);

      // Attempt reconnect after 3 seconds (only for unexpected closes)
      if (closeEvent.code !== 1000) {
        reconnectTimeoutRef.current = setTimeout(() => {
          log.debug("Attempting HeroDraft WebSocket reconnect...");
          connect();
        }, 3000);
      }
    };

    ws.onerror = (error) => {
      log.error("HeroDraft WebSocket error:", error);
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
    isConnected,
    connectionError,
  };
}
