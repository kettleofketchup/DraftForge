import { useCallback, useEffect, useRef, useState } from "react";
import { getLogger } from "~/lib/logger";
import type { HeroDraft, HeroDraftEvent, HeroDraftTick } from "../types";
import { HeroDraftWebSocketMessageSchema } from "../schemas";

const log = getLogger("useHeroDraftWebSocket");

// Enable verbose debug logging for HeroDraft debugging
const DEBUG = true;
const debugLog = (...args: unknown[]) => {
  if (DEBUG) {
    console.log("[HeroDraftWS]", ...args);
  }
};

// Reconnection configuration
const RECONNECT_BASE_DELAY_MS = 1000;  // Start with 1 second
const RECONNECT_MAX_DELAY_MS = 30000;  // Max 30 seconds
const RECONNECT_MAX_ATTEMPTS = 10;     // Give up after 10 attempts

interface UseHeroDraftWebSocketOptions {
  draftId: number | null;
  enabled?: boolean;  // Only connect when enabled (default: true when draftId is set)
  onStateUpdate?: (draft: HeroDraft) => void;
  onTick?: (tick: HeroDraftTick) => void;
  onEvent?: (event: HeroDraftEvent) => void;
}

interface UseHeroDraftWebSocketReturn {
  isConnected: boolean;
  connectionError: string | null;
  reconnectAttempts: number;
  reconnect: () => void;
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
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const shouldConnectRef = useRef(false);
  const connectionIdRef = useRef(0); // Track connection ID to ignore stale callbacks
  const intentionalCloseRef = useRef(false); // Track if we intentionally closed the connection

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
        intentionalCloseRef.current = true;
        ws.close(1000, "Stale connection");
        return;
      }
      log.debug("HeroDraft WebSocket connected");
      setIsConnected(true);
      setConnectionError(null);
      setReconnectAttempts(0); // Reset reconnect attempts on successful connection
    };

    ws.onmessage = (messageEvent) => {
      // Ignore if this is a stale connection
      if (connectionIdRef.current !== thisConnectionId) {
        log.debug("Ignoring stale WebSocket message");
        return;
      }
      try {
        const rawData = JSON.parse(messageEvent.data);

        // Debug: Log raw data before validation
        debugLog("Raw message data:", typeof rawData, Array.isArray(rawData) ? `Array(${rawData.length})` : rawData?.type, rawData);

        // Validate with Zod for runtime type safety
        const parseResult = HeroDraftWebSocketMessageSchema.safeParse(rawData);
        if (!parseResult.success) {
          log.warn("Invalid WebSocket message format:", parseResult.error.issues);
          log.warn("Raw message that failed validation:", JSON.stringify(rawData, null, 2));
          return;
        }

        const data = parseResult.data;
        debugLog("Message received:", data.type, data);

        switch (data.type) {
          case "initial_state":
            // Full state replace on connect/reconnect - prevents state drift
            debugLog("initial_state received", {
              state: data.draft_state.state,
              current_round: data.draft_state.current_round,
              rounds_count: data.draft_state.rounds.length,
              active_rounds: data.draft_state.rounds.filter(r => r.state === "active").map(r => r.round_number),
            });
            if (onStateUpdateRef.current) {
              onStateUpdateRef.current(data.draft_state);
            }
            break;

          case "herodraft_event":
            debugLog("herodraft_event received", {
              event_type: data.event_type,
              draft_team_id: data.draft_team?.id,
              draft_team_captain: data.draft_team?.captain?.username,
              has_draft_state: !!data.draft_state,
              draft_state: data.draft_state?.state,
              current_round: data.draft_state?.current_round,
              active_rounds: data.draft_state?.rounds.filter(r => r.state === "active").map(r => r.round_number),
            });
            if (data.draft_state && onStateUpdateRef.current) {
              debugLog("Calling onStateUpdate with state:", data.draft_state.state, "current_round:", data.draft_state.current_round);
              onStateUpdateRef.current(data.draft_state);
            } else if (!data.draft_state) {
              log.warn("herodraft_event missing draft_state - UI may not update");
            }
            if (data.event_type && onEventRef.current) {
              // Pass full event data including draft_team object and metadata
              onEventRef.current(data);
            }
            break;

          case "herodraft_tick":
            debugLog("herodraft_tick received", {
              current_round: data.current_round,
              active_team_id: data.active_team_id,
              grace_time_remaining_ms: data.grace_time_remaining_ms,
              team_a_reserve_ms: data.team_a_reserve_ms,
              team_b_reserve_ms: data.team_b_reserve_ms,
              draft_state: data.draft_state,
            });
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

      // Check if this was an intentional close (we called close() ourselves)
      const wasIntentional = intentionalCloseRef.current;
      intentionalCloseRef.current = false; // Reset for next connection

      // Attempt reconnect if:
      // 1. We didn't intentionally close it
      // 2. We should still be connected (component is mounted and enabled)
      // 3. We haven't exceeded max reconnect attempts
      if (!wasIntentional && shouldConnectRef.current) {
        setReconnectAttempts(prev => {
          const newAttempts = prev + 1;

          if (newAttempts > RECONNECT_MAX_ATTEMPTS) {
            log.error(`Max reconnect attempts (${RECONNECT_MAX_ATTEMPTS}) exceeded, giving up`);
            setConnectionError(`Connection lost. Max reconnection attempts exceeded.`);
            return newAttempts;
          }

          // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s, 30s...
          const delay = Math.min(
            RECONNECT_BASE_DELAY_MS * Math.pow(2, newAttempts - 1),
            RECONNECT_MAX_DELAY_MS
          );

          log.debug(`Scheduling reconnect attempt ${newAttempts}/${RECONNECT_MAX_ATTEMPTS} in ${delay}ms`);
          setConnectionError(`Connection lost. Reconnecting in ${Math.round(delay / 1000)}s...`);

          reconnectTimeoutRef.current = setTimeout(() => {
            log.debug(`Attempting HeroDraft WebSocket reconnect (attempt ${newAttempts})...`);
            connect();
          }, delay);

          return newAttempts;
        });
      } else if (wasIntentional) {
        log.debug("WebSocket closed intentionally, not reconnecting");
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
        intentionalCloseRef.current = true; // Mark as intentional close
        wsRef.current.close(1000, "Connection disabled");
        wsRef.current = null;
      }
      setIsConnected(false);
      setConnectionError(null);
      setReconnectAttempts(0);
    }

    return () => {
      shouldConnectRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        // Close WebSocket regardless of state - don't leave orphaned CONNECTING sockets
        // Calling close() on CONNECTING socket will abort it cleanly
        intentionalCloseRef.current = true; // Mark as intentional close
        wsRef.current.close(1000, "Component unmounting");
        wsRef.current = null;
      }
    };
  }, [connect, enabled, draftId]);

  // Manual reconnect function
  const reconnect = useCallback(() => {
    log.info("Manual reconnect requested");

    // Close existing connection if any
    if (wsRef.current) {
      intentionalCloseRef.current = true; // Mark as intentional close
      wsRef.current.close(1000, "Manual reconnect");
      wsRef.current = null;
    }

    // Clear any pending reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    setIsConnected(false);
    setConnectionError(null);
    setReconnectAttempts(0); // Reset attempts on manual reconnect

    // Attempt reconnect after a brief delay
    setTimeout(() => {
      if (shouldConnectRef.current && draftId) {
        connect();
      }
    }, 100);
  }, [connect, draftId]);

  return {
    isConnected,
    connectionError,
    reconnectAttempts,
    reconnect,
  };
}
