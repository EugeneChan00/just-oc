/**
 * Shared notification types for cross-surface communication.
 * Imported by: backend WebSocket server, frontend notification panel, agentic event-router.
 */

/**
 * NotificationEvent — the message schema shared across all surfaces
 */
export interface NotificationEvent {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  timestamp: number;
  source: string;
}

/**
 * Subscription — returned by subscribe(), used for channel subscription management
 */
export interface Subscription {
  unsubscribe(): void;
}
