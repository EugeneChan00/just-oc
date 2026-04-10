/**
 * Shared health status types for cross-surface communication.
 * Imported by: backend REST endpoint (src/api/routes/agent-health.ts),
 * agent plane event-loop (agents/health-checker/event-loop.ts).
 */

/**
 * HealthMetrics — numeric health indicators collected from an agent
 */
export interface HealthMetrics {
  responseTime: number;   // milliseconds
  errorRate: number;     // 0-1 ratio (errors / total requests)
  memoryUsage: number;    // bytes
}

/**
 * Agent health status enumeration
 */
export type HealthStatusValue = 'healthy' | 'degraded' | 'unhealthy';

/**
 * HealthStatus — the shared health report schema emitted by the health-checker
 * and consumed by the backend REST endpoint.
 */
export interface HealthStatus {
  agentId: string;
  status: HealthStatusValue;
  metrics: HealthMetrics;
  timestamp: Date;
}

/**
 * HealthCheckResult — latest results container written by the event-loop
 * and read by the REST endpoint via the integration store.
 */
export interface HealthCheckResult {
  results: HealthStatus[];
  lastUpdated: Date;
}
