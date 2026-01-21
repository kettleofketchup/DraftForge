import { useCallback, useEffect, useRef, useState } from "react";
import { getLogger } from "~/lib/logger";
import type { HeroDraft, HeroDraftTick } from "../types";
import { HeroDraftWebSocketMessageSchema } from "../schemas";

const log = getLogger("useHeroDraftWebSocket");

interface UseHeroDraftWebSocketOptions {
  draftId: number | null;
  enabled?: boolean;  // Only connect when enabled (default: true when draftId is set)
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
  enabled = true,
  onStateUpdate,
  onTick,
  onEvent,
}: UseHeroDraftWebSocketOptions): UseHeroDraftWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const shouldConnectRef = useRef(false);
  const connectionIdRef = useRef(0); // Track connection ID to ignore stale callbacks

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
    if (!draftId || !shouldConnectRef.current) {
      log.debug("WebSocket connect skipped", { draftId, enabled: shouldConnectRef.current });
      return;
    }

    // Don't reconnect if already connected or connecting
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      log.debug("WebSocket already connected/connecting, skipping reconnect");
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/herodraft/${draftId}/`;

    log.debug(`Connecting to HeroDraft WebSocket: ${wsUrl}`);

    // Increment connection ID to track this specific connection
    const thisConnectionId = ++connectionIdRef.current;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      // Ignore if this is a stale connection (component remounted)
      if (connectionIdRef.current !== thisConnectionId) {
        log.debug("Ignoring stale WebSocket open");
        ws.close(1000, "Stale connection");
        return;
      }
      log.debug("HeroDraft WebSocket connected");
      setIsConnected(true);
      setConnectionError(null);
    };

    ws.onmessage = (messageEvent) => {
      // Ignore if this is a stale connection
      if (connectionIdRef.current !== thisConnectionId) {
        log.debug("Ignoring stale WebSocket message");
        return;
      }
      try {
        const rawData = JSON.parse(messageEvent.data);

        // Validate with Zod for runtime type safety
        const parseResult = HeroDraftWebSocketMessageSchema.safeParse(rawData);
        if (!parseResult.success) {
          log.warn("Invalid WebSocket message format:", parseResult.error.issues);
          log.debug("Raw message:", rawData);
          return;
        }

        const data = parseResult.data;
        log.debug("HeroDraft WebSocket message:", data);

        switch (data.type) {
          case "initial_state":
            // Full state replace on connect/reconnect - prevents state drift
            if (onStateUpdateRef.current) {
              log.debug("Received initial_state - replacing full draft state");
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
            if (onTickRef.current) {
              onTickRef.current({
                type: "herodraft_tick",
                current_round: data.current_round,
                active_team_id: data.active_team_id,
                grace_time_remaining_ms: data.grace_time_remaining_ms,
                team_a_id: data.team_a_id,
                team_a_reserve_ms: data.team_a_reserve_ms,
                team_b_id: data.team_b_id,
                team_b_reserve_ms: data.team_b_reserve_ms,
                draft_state: data.draft_state,
              });
            }
            break;
        }
      } catch (err) {
        log.error("Failed to parse HeroDraft WebSocket message:", err);
      }
    };

    ws.onclose = (closeEvent) => {
      // Ignore if this is a stale connection
      if (connectionIdRef.current !== thisConnectionId) {
        log.debug("Ignoring stale WebSocket close");
        return;
      }
      log.debug("HeroDraft WebSocket closed:", closeEvent.code, closeEvent.reason);
      setIsConnected(false);

      // Attempt reconnect after 3 seconds (only for unexpected closes)
      if (closeEvent.code !== 1000 && shouldConnectRef.current) {
        reconnectTimeoutRef.current = setTimeout(() => {
          log.debug("Attempting HeroDraft WebSocket reconnect...");
          connect();
        }, 3000);
      }
    };

    ws.onerror = (error) => {
      // Ignore if this is a stale connection (e.g., StrictMode double-mount)
      if (connectionIdRef.current !== thisConnectionId) {
        log.debug("Ignoring stale WebSocket error");
        return;
      }
      log.error("HeroDraft WebSocket error:", error);
      setConnectionError("Connection error");
    };
  }, [draftId]); // Only depend on draftId - callbacks are accessed via refs

  // Manage connection based on enabled state
  useEffect(() => {
    shouldConnectRef.current = enabled;

    if (enabled && draftId) {
      connect();
    } else {
      // Disconnect if disabled
      if (wsRef.current) {
        wsRef.current.close(1000, "Connection disabled");
        wsRef.current = null;
      }
      setIsConnected(false);
      setConnectionError(null);
    }

    return () => {
      shouldConnectRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        // Only close if actually connected - prevents StrictMode double-mount issues
        // where WebSocket gets closed before connection is established
        if (wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.close(1000, "Component unmounting");
        }
        // Clear ref regardless - let CONNECTING sockets fail naturally
        wsRef.current = null;
      }
    };
  }, [connect, enabled, draftId]);

  return {
    isConnected,
    connectionError,
  };
}
