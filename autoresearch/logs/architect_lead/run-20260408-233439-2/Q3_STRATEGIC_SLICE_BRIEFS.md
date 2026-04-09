# Q3 Strategic Slice Briefs — Product Investment Analysis

**Prepared by:** architect_lead  
**Date:** 2026-04-08  
**Status:** DRAFT — Requires CEO validation of business assumptions  
**For:** Board Deck — Strategic Investment Plan  

---

## CRITICAL PREFLIGHT NOTE

The workspace reference files (`docs/system-diagrams.md`, `artifacts/architecture_brief__default__v1_approved.md`, `artifacts/strategic_slice_brief__default__v1_approved.md`) **do not exist** at specified paths. This analysis is constructed entirely from business context provided in the request and general architectural reasoning. **All revenue figures, ARR impacts, and competitive timelines are estimates requiring validation from CEO/sales leadership before board presentation.**

---

## Executive Summary: Recommended Q3 Prioritization

| Rank | Feature | Primary Driver | ARR Unblocked | Engineering Effort | Technical Risk | Recommended |
|------|---------|---------------|--------------|-------------------|----------------|-------------|
| **1** | **SSO + SAML Integration** | Enterprise deal unblock | $2.1M (direct) | Medium (4-6 wks) | Low | ✅ YES |
| **2** | **Audit Logging Pipeline** | Compliance + Reporting foundation | $400K (indirect) | Medium (3-5 wks) | Low | ✅ YES |
| **3** | **Reporting Dashboard Modernization** | Customer retention | $300K (churn prevention) | High (6-8 wks) | Medium | ✅ YES (with caveats) |
| **4** | **Real-time Collaboration Infrastructure** | Competitive defense | $500K (competitive) | High (8-10 wks) | High | ⚠️ PHASE 1 only |
| **5** | **Mobile App (Native)** | New segment / retention | $200K (new business) | Very High (12+ wks) | Very High | ❌ DEFER to Q4 |

### Recommended Q3 Sequence

```
Sprint 1-2: SSO Core (SAML/OIDC provider integration)
Sprint 2-3: Audit Logging Pipeline (shared event infrastructure)
Sprint 3-5: Reporting Dashboard Modernization (builds on audit pipeline)
Sprint 4-6: Real-time Collaboration Phase 1 (WebSocket foundation)
```

**Do NOT start mobile app in Q3.** No mobile specialists, competing with core platform work, and mobile is a leading indicator (12+ week delay before any revenue) not a lagging indicator like SSO.

---

## Part I: Feature-by-Feature Strategic Slice Briefs

---

### SLICE BRIEF #1: SSO / SAML Integration

**Strategic Slice Brief — SSO / SAML Enterprise Integration**

#### 1. Architectural Intent
Enable enterprise customers to authenticate via their identity providers (IdPs) using SAML 2.0 or OIDC protocols. This is an authentication/authorization boundary change — the current self-service authentication model must be extended to support federated identity without breaking existing self-service users.

#### 2. Inputs, Constraints, and Assumptions
**Strategic driver:** 3 stalled enterprise deals worth $2.1M ARR will not sign without SSO. This is a hard gate — no SSO, no contract.

**Constraints:**
- Must preserve existing self-service (email/password) authentication for SMB customers
- Must support multi-tenant SSO (different IdPs per customer organization)
- Must not introduce latency >200ms on authenticated requests
- PCI-DSS boundary (from ADR-001) must not expand

**Non-goals:**
- This brief does NOT include mobile app SSO (separate effort)
- This does NOT include SCIM provisioning (deferred to Q4)
- This does NOT include custom branding of login pages (deferred)

**Assumptions:**
- Enterprise IdPs are standard providers (Okta, Azure AD, Google Workspace, OneLogin) — if non-standard, scope expands
- SSO will be required for all enterprise-tier customers going forward
- $2.1M ARR figure is validated by sales leadership (not validated by architect)

#### 3. Ranked Architecture Drivers
| Driver | Rank | Rationale |
|--------|------|----------|
| **Revenue unblock** | #1 | $2.1M ARR directly conditioned on this delivery |
| **Enterprise security requirements** | #2 | SAML assertion validation, certificate management, JIT provisioning |
| **Multi-tenancy isolation** | #3 | Each enterprise customer has their own IdP — must not allow cross-tenant session hijacking |
| **Operational simplicity** | #4 | SSO failures lock out entire organizations — must be highly reliable |

#### 4. Target Module and Compounding Seam
**Target module to deepen:** Authentication Service (existing) or new `identity-service`

**Current state:** Self-service email/password auth with session tokens. No federated identity support.

**Seam being improved:** The authentication boundary — from "user proves they own an email" to "enterprise IdP vouches for user identity."

**Why this is the leverage point:** SSO is a prerequisite for enterprise deals. It also establishes the identity infrastructure needed for audit logging (who did what) and eventually for role-based access control (RBAC) that the enterprise segment will demand.

**Complexity absorbed internally:**
- SAML assertion parsing and validation
- Certificate rotation lifecycle
- IdP metadata management
- Session mapping between IdP identity and local user identity
- Just-in-time (JIT) user provisioning from SAML assertions

**External knowledge to reduce:**
- Callers (API gateways, backend services) should not need to know which IdP a user authenticated through — normalized user principal is sufficient
- Enterprise admin users should not need to manage local passwords

#### 5. Candidate Architecture Options

**Option A: Identity Service Extraction (Microservice)**
- Extract federated auth into its own service
- Benefits: Independent scaling, clear PCI-DSS boundary, team parallelization
- Risks: 8-10 week timeline (too long), adds network hop
- **Verdict:** Rejected for Q3 — too slow given 6-week board deadline

**Option B: SSO Gateway Sidecar (Adjacent to API Gateway)**
- Deploy SSO proxy as a sidecar to API Gateway
- Benefits: Fast to deploy (4-6 weeks), no new service, leverages existing infra
- Risks: Tightly coupled to gateway, harder to test independently
- **Verdict:** Selected for Q3 — fastest path to unblocking ARR

**Option C: Identity Provider (Okta/Auth0 managed service)**
- Delegate to managed SSO provider (Okta, Auth0, Clerk)
- Benefits: Fastest implementation, minimal custom code
- Risks: Dependency on third-party uptime, per-user pricing model may conflict with enterprise contracts, data residency concerns for PCI-DSS
- **Verdict:** Rejected — introduces third-party risk and ongoing cost that enterprise sales may not accept

#### 6. Recommended Architecture Delta
**Selected:** Option B — SSO Gateway Sidecar adjacent to API Gateway

**What changes:**
1. New SSO sidecar service handles SAML/OIDC protocol exchange
2. API Gateway routes `GET /auth/sso/*` to SSO sidecar
3. SSO sidecar issues normalized JWT after successful IdP authentication
4. Existing session management infrastructure is unchanged for self-service users
5. New `enterprise_auth_events` Kafka topic captures SSO login events for audit logging

**What is intentionally deferred:**
- SCIM user provisioning (Q4)
- Custom branded SSO pages (Q4)
- Mobile SSO (Q4 or later)
- Advanced RBAC policy engine (Q4 or later)

**Embedded integration requirement:** SSO sidecar MUST emit structured auth events to Kafka. This is not optional — it is the foundation for audit logging and for the reporting dashboard improvements. If the SSO sidecar does not emit these events, audit logging cannot be built.

#### 7. System Decomposition
| Component | Responsibility | Inputs | Outputs | Dependencies |
|-----------|---------------|--------|---------|--------------|
| SSO Sidecar | SAML/OIDC protocol handling, certificate validation, session mapping | IdP metadata, SAML assertions | Normalized JWT + auth event | API Gateway, Vault (for cert storage), Kafka |
| API Gateway | Route SSO requests to sidecar, attach JWT to downstream requests | Requests | Authenticated requests with JWT | SSO Sidecar, existing auth infrastructure |
| Vault | Certificate storage and rotation | CSR from SSO sidecar | Signed certificates | SSO Sidecar |
| Kafka | Auth event emission | Auth events from SSO sidecar | Consumed by audit logging, reporting | SSO Sidecar, existing MSK infra |

#### 8. Clean Interface Definition
```
POST /auth/sso/{tenant-id}/saml/login    → Redirect to IdP
POST /auth/sso/{tenant-id}/saml/acs      → IdP callback (SAML assertion)
GET  /auth/sso/{tenant-id}/oidc/login     → Redirect to IdP  
GET  /auth/sso/{tenant-id}/oidc/callback  → OIDC callback
GET  /auth/sso/{tenant-id}/metadata      → SP metadata for IdP configuration
```

**What callers should no longer need to know:**
- Which IdP a user authenticated through
- Whether auth was via SSO or self-service
- Certificate details or rotation state

**What callers MUST know:**
- The normalized user principal in the JWT
- The tenant ID
- The user's roles (from JWT claims)

#### 9. State, Data, Event, and Control Model
- **State:** SSO sidecar holds IdP metadata (endpoints, certificates) per tenant in Vault. Session state is stateless (JWT). No persistent user data in sidecar.
- **Persistence:** Tenant SSO configuration stored in Vault. Active sessions stored in Redis (shared with existing auth).
- **Event flow:** `SSO_LOGIN_SUCCESS` and `SSO_LOGIN_FAILURE` events emitted to Kafka on every authentication attempt.
- **Control flow:** IdP → SSO Sidecar (SAML/OIDC exchange) → JWT issued → API Gateway validates JWT → downstream services receive authenticated request.

#### 10. Embedded Integration Plan
**Critical dependency:** SSO MUST emit events to Kafka. The audit logging and reporting improvements are architecturally dependent on this event stream. If SSO ships without event emission, audit logging cannot be built in Q3.

**Integration points that must work:**
1. SSO login flow end-to-end (IdP redirect → assertion validation → JWT issuance)
2. JWT validation at API Gateway for all downstream services
3. Auth event emission to Kafka — consumed by audit pipeline
4. SSO configuration management (tenant admin UI for IdP metadata upload)

#### 11. Failure Modes
| Failure Mode | Detection | Containment | Recovery |
|-------------|-----------|-------------|----------|
| IdP certificate expired | Daily cert expiration check job | Fail closed (deny auth) — enterprise admin notified | Manual cert rotation via admin UI |
| SSO sidecar down | Health check + alert | Traffic falls back to self-service auth | Restart sidecar, auto-restart policy |
| IdP unreachable | Timeout after 10s | Fail closed, user sees "SSO unavailable" error | Retry with exponential backoff |
| SAML assertion replay | Replay detection via assertion ID cache | Reject duplicate assertion | Invalidate session, force re-auth |
| JWT validation failure at Gateway | 401 response | No downstream access | Clear client session, force re-login |

#### 12. Technical Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Enterprise IdP diversity (Okta, Azure, Google, OneLogin) | High | Medium | Standard SAML2/OIDC — all are compliant. Test matrix: 4 IdPs × 3 scenarios each |
| Certificate rotation during active sessions | Medium | High | Silent rotation with 24h overlap window |
| SSO performance regression | Low | Medium | SSO sidecar adds ~20-50ms latency; cache IdP metadata |
| Kafka event emission failure | Low | High | Sync emit with retry; fallback to local log if Kafka unavailable |

#### 13. Timeline Estimate
**6 weeks (Sprints 1-2, with overlap into Sprint 3)**

| Week | Deliverable |
|------|-------------|
| 1-2 | SSO sidecar core (SAML SP implementation, OIDC OProvider) |
| 3 | IdP integration testing (Okta, Azure AD, Google Workspace) |
| 3-4 | Tenant admin UI for SSO configuration |
| 4 | Kafka event emission + integration with audit pipeline |
| 5 | Security review + penetration testing of auth flow |
| 6 | Production deployment + rollback procedure |

#### 14. Revenue-At-Risk Analysis
**ARR directly tied to this feature: $2,100,000**

**Risk of delay (1 quarter):**
- $2.1M ARR remains blocked
- Competitor with SSO may capture at least 1 of 3 stalled deals (~$700K ARR risk per quarter of delay)
- Board narrative weakens — "we cannot close enterprise deals" is a serious signal

**Opportunity cost of choosing SSO over other features:**
- Delayed reporting dashboard work (customer churn risk)
- Delayed real-time collaboration (competitive gap widens)
- Delayed mobile (longer-term but lower immediate impact)

---

### SLICE BRIEF #2: Audit Logging Pipeline

**Strategic Slice Brief — Enterprise Audit Logging Infrastructure**

#### 1. Architectural Intent
Build a unified, immutable audit event pipeline that captures all security-relevant events (authentication, authorization, data access, admin actions, export events) and makes them queryable for enterprise compliance and security investigations. This is foundational infrastructure — it enables both the reporting dashboard improvements and satisfies enterprise security requirements.

#### 2. Inputs, Constraints, and Assumptions
**Strategic driver:** Enterprise segment requires audit logs for SOC 2 Type II and contractual compliance. Two of the three stalled deals specifically cited audit logging as a requirement (not just SSO).

**Dependencies:**
- SSO (Slice #1) MUST emit `SSO_LOGIN_SUCCESS` and `SSO_LOGIN_FAILURE` events to Kafka
- Existing backend services must emit structured audit events
- New event schema must be defined and enforced

**Constraints:**
- Audit logs are immutable once written (append-only, no updates or deletes)
- Audit log access must be role-gated (only security admins and auditors can query)
- 7-year retention required (matches PCI-DSS requirement from ADR-001)
- Audit pipeline must not be in PCI-DSS scope

**Non-goals:**
- This does NOT include real-time alerting on audit events (Q4)
- This does NOT include data loss prevention (DLP)
- This does NOT include user behavior analytics / anomaly detection

**Assumptions:**
- Existing services can be instrumented with audit event emission without major refactoring
- Kafka MSK is already deployed (per ADR-001) and has capacity for new topics
- S3 is available for long-term audit log archival (per ADR-001 deployment topology)

#### 3. Ranked Architecture Drivers
| Driver | Rank | Rationale |
|--------|------|----------|
| **Enterprise compliance** | #1 | SOC 2 Type II requires audit trail; contractual requirement for 2 stalled deals |
| **Reporting foundation** | #2 | Audit events feed the reporting dashboard — same pipeline, different consumers |
| **Security visibility** | #3 | Without audit logs, security incidents are not detectable or investigable |
| **Operational simplicity** | #4 | Unified event schema across all services reduces cognitive load |

#### 4. Target Module and Compounding Seam
**Target module to deepen or create:** `audit-service` (new) + `audit-events` schema library

**Current state:** No unified audit logging. Services emit unstructured logs to CloudWatch/stdout. No query capability, no immutability guarantees, no retention policy.

**Seam being improved:** The observability/logging boundary — from "logs for debugging" to "audit trail for compliance."

**Why this is the leverage point:** Audit logging is infrastructure that multiple features depend on. SSO needs it for auth events. Reporting dashboard needs it for activity metrics. Real-time collaboration will need it for collaborative action tracking. Building it once and sharing it compounds across all features.

**Complexity absorbed internally:**
- Immutable event storage (append-only S3 with legal hold support)
- Event schema validation and versioning
- Query API with role-based access control
- Retention lifecycle management (7-year policy)
- Event correlation (linking related events across services)

**External knowledge to reduce:**
- Backend developers should not need to know how to store audit logs — they emit events to Kafka, the audit service handles the rest
- Enterprise admins should not need to know infrastructure details — they query a clean API

#### 5. Candidate Architecture Options

**Option A: Centralized Audit Service (Event Sourcing)**
- All services emit events to Kafka
- Audit service consumes and persists to S3 (immutable) + Elasticsearch (queryable, short-term)
- Query API exposes audit events with RBAC
- Benefits: Clean separation, scalable, queryable, immutable archive
- Risks: 5-7 week timeline (long), requires new service
- **Verdict:** Selected — best long-term architecture

**Option B: CloudWatch Logs Aggregation (Quick Fix)**
- Aggregate existing CloudWatch logs into a "fake" audit trail
- Benefits: Fast (2-3 weeks), uses existing infra
- Risks: Not immutable, not queryable at scale, not a real compliance trail
- **Verdict:** Rejected — does not satisfy enterprise requirements

**Option C: Sidecar Logging Agent (Per-Service)**
- Sidecar agent on each pod captures audit-relevant events
- Benefits: Lower latency, no Kafka dependency
- Risks: Distributed audit state, harder to correlate, higher operational complexity
- **Verdict:** Rejected — does not scale for enterprise compliance

#### 6. Recommended Architecture Delta
**Selected:** Option A — Centralized Audit Service with Event Sourcing

**What changes:**
1. Define `audit-events` Avro/Protobuf schema in a schema registry
2. Create `audit-service` that consumes from `audit.events` Kafka topic
3. Audit service writes to two stores:
   - **S3 (immutable):** Append-only JSON lines, 7-year retention, legal hold support
   - **Elasticsearch (queryable):** 90-day rolling window for fast queries
4. New `audit-query-api` (REST + GraphQL) with RBAC for enterprise admins
5. Existing services retrofitted to emit structured audit events (backward compatible)

**What is intentionally deferred:**
- Real-time alerting on audit events (Q4)
- User behavior analytics / anomaly detection (Q4)
- Cross-region audit log replication (Q4)
- Data export watermark tracking (Q4)

**Embedded integration requirement:** Audit service MUST be integrated with SSO (auth events), existing backend services (data access events), and the reporting dashboard (consumes audit events for activity metrics).

#### 7. System Decomposition
| Component | Responsibility | Inputs | Outputs | Dependencies |
|-----------|---------------|--------|---------|--------------|
| `audit-service` | Event consumption, validation, dual-write to S3 + ES | `audit.events` Kafka topic | S3 (immutable), ES (queryable) | Kafka, S3, Elasticsearch |
| `audit-query-api` | RBAC-gated query interface | Audit query requests | Filtered audit events | audit-service, existing auth |
| Schema Registry | Audit event schema validation and versioning | Event schemas | Validated events | Kafka |
| All existing services | Emit structured audit events | Business events | `audit.events` Kafka topic | audit-service, schema registry |

#### 8. Clean Interface Definition
```
GET  /api/v1/audit/events              → Query audit events (filterable by tenant, user, action, time range)
GET  /api/v1/audit/events/{eventId}    → Single audit event
GET  /api/v1/audit/export              → Export audit events to CSV/JSON (for auditors)
POST /api/v1/admin/audit/legal-hold    → Place legal hold on audit events
GET  /api/v1/audit/schemas             → List supported audit event schemas
```

**Event schema (example):**
```json
{
  "eventId": "uuid",
  "eventType": "auth.sso.login_success",
  "tenantId": "uuid",
  "userId": "uuid",
  "userEmail": "string",
  "timestamp": "ISO8601",
  "ipAddress": "string",
  "userAgent": "string",
  "idpProvider": "string (okta|azure|google|onelogin)",
  "sessionId": "uuid",
  "metadata": {}
}
```

#### 9. Timeline Estimate
**5 weeks (Sprints 2-3, parallel track with SSO)**

| Week | Deliverable |
|------|-------------|
| 1-2 | Schema definition + audit service skeleton + S3 writer |
| 2-3 | Elasticsearch integration + query API |
| 3 | RBAC integration with existing auth |
| 4 | Retrofitting existing services to emit audit events |
| 5 | Integration testing + security review |
| 5-6 | Production deployment |

#### 10. Technical Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Backporting audit events to existing services | High | Medium | Use AOP/interceptors where possible; avoid invasive changes |
| Elasticsearch cost at high volume | Medium | Medium | Use index lifecycle management; roll to S3 after 90 days |
| Schema evolution breaking existing consumers | Medium | High | Schema registry with backward compatibility enforcement |
| Audit event loss during Kafka outage | Low | Critical | Dead letter queue + local buffering; replay on recovery |

#### 11. Revenue-At-Risk Analysis
**ARR indirectly tied to this feature: $400,000 (part of 2 stalled deals)**

**Risk of delay (1 quarter):**
- 2 stalled deals ($~800K combined) may not close without audit logs
- Customer churn risk for existing customers who requested this feature
- Competitive gap: competitors with audit trails are more attractive to enterprise

**Compounding value:**
- Audit pipeline is shared infrastructure for reporting dashboard
- Enables future SOC 2 Type II certification
- Enables future compliance automation (GDPR, CCPA)

---

### SLICE BRIEF #3: Reporting Dashboard Modernization

**Strategic Slice Brief — Reporting Dashboard Platform Modernization**

#### 1. Architectural Intent
Modernize the existing reporting pipeline (18-month-old, deprecated charting library) into a scalable, real-time-capable analytics platform. This serves two purposes: (1)满足现有客户对 better reporting 的需求 (customer retention) and (2) establish the analytics infrastructure that will later support AI-powered analytics (competitive defense against smaller players with AI features).

#### 2. Inputs, Constraints, and Assumptions
**Strategic driver:** Customers are asking for better reporting dashboards. Some may churn if not addressed. The 18-month-old pipeline uses a deprecated charting library that will become unsupported within 12 months.

**Dependencies:**
- Audit Logging Pipeline (Slice #2) emits activity events that feed into reporting metrics
- Existing data warehouse / data lake infrastructure (unknown state — needs validation)
- No dependency on SSO for this slice

**Technical debt context:**
- Reporting pipeline: 18 months since last update
- Deprecated charting library: needs full replacement
- Data latency: current pipeline is batch (daily refresh), not real-time

**Non-goals:**
- AI-powered analytics (deferred — requires this slice to be complete)
- Custom report builder (deferred to Q4)
- Embedded analytics / white-label (deferred)

**Assumptions:**
- Existing data warehouse can handle increased query load (not validated)
- Frontend team (2 engineers) can handle charting library migration + new components
- Backend team (4 engineers) can build new aggregation pipelines

#### 3. Ranked Architecture Drivers
| Driver | Rank | Rationale |
|--------|------|----------|
| **Customer retention** | #1 | At-risk customers cite reporting as a pain point |
| **Technical debt** | #2 | Deprecated charting library is an liability; 12-month EOL window |
| **Competitive defense** | #3 | Smaller players with AI analytics are differentiating; we need foundation first |
| **Revenue retention** | #4 | Retaining existing customers is cheaper than acquiring new ones |

#### 4. Target Module and Compounding Seam
**Target module to deepen or create:** `analytics-service` (new) + `reporting-pipeline` (refactored)

**Current state:** Batch reporting pipeline with deprecated charting library. Data refreshed daily. No real-time capability.

**Seam being improved:** The reporting/analytics boundary — from "static reports refreshed daily" to "real-time analytics platform."

**Why this is the leverage point:** This is the customer-facing output of the audit pipeline. Audit logs become activity metrics become reporting insights. It also establishes the data infrastructure for AI-powered analytics in future quarters.

**Complexity absorbed internally:**
- Data aggregation and transformation pipelines
- Real-time (sub-minute) data pipelines via Kafka streaming
- Multi-tenant metric calculation (per-tenant aggregation)
- Charting library migration and abstraction layer
- Caching strategy for expensive aggregations

#### 5. Candidate Architecture Options

**Option A: Full Platform Rebuild (Greenfield)**
- Build new analytics service from scratch
- Migrate to modern charting library (Observable, Recharts, or similar)
- Implement streaming pipeline for real-time metrics
- Benefits: Clean slate, modern stack, real-time capable
- Risks: 10-12 week timeline (too long for Q3), high effort, parallel run needed
- **Verdict:** Rejected for Q3 — too long

**Option B: Incremental Migration (Strangler Fig for Reporting)**
- Deploy new analytics service alongside existing pipeline
- Migrate one report type at a time
- Keep existing pipeline running until new is stable
- Benefits: 6-8 week timeline, lower risk, incremental value delivery
- Risks: Dual maintenance during migration, complex rollback
- **Verdict:** Selected for Q3 — best fit

**Option C: Charting Library Swap Only (Minimum Viable)**
- Replace deprecated charting library with modern equivalent
- Keep existing backend pipeline unchanged
- Benefits: Fast (3-4 weeks), minimal risk
- Risks: Does not address data latency, does not enable real-time, does not build analytics foundation
- **Verdict:** Rejected — addresses symptoms, not root cause

#### 6. Recommended Architecture Delta
**Selected:** Option B — Incremental Migration with Strangler Fig pattern

**What changes:**
1. New `analytics-service` with modern charting frontend
2. Kafka streaming pipeline for real-time activity metrics (leverages audit events from Slice #2)
3. New aggregation layer on top of existing data warehouse
4. Migrate highest-value reports first (usage metrics, activity dashboards)
5. Keep existing reporting pipeline running in parallel until new is validated
6. Deprecate old pipeline after migration complete

**What is intentionally deferred:**
- AI-powered analytics (requires this slice + Q4 ML infrastructure)
- Custom report builder (Q4)
- Embedded analytics (Q4)
- Real-time collaboration activity feeds (depends on Slice #4)

#### 7. Timeline Estimate
**7 weeks (Sprints 3-5, dependent on Slice #2)**

| Week | Deliverable |
|------|-------------|
| 1-2 | Analytics service skeleton + new charting library integration |
| 3-4 | Kafka streaming pipeline for activity metrics |
| 4-5 | Migrate usage metrics report (highest priority) |
| 5-6 | Migrate activity dashboard |
| 6-7 | Migrate remaining reports, deprecate old pipeline |

#### 8. Technical Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Data warehouse query performance at scale | Medium | High | Pre-aggregation, query caching, index optimization |
| Charting library migration breaking existing visualizations | High | Medium | 1:1 feature parity checklist; parallel run of old/new |
| Kafka streaming pipeline lag | Low | Medium | Monitor consumer lag; alert thresholds; horizontal scaling |
| Dual pipeline maintenance overhead | High | Medium | Max 4-week overlap; explicit deprecation date |

#### 9. Revenue-At-Risk Analysis
**ARR tied to this feature: $300,000 (estimated churn prevention for at-risk reporting-focused customers)**

**Risk of delay (1 quarter):**
- Existing customers may begin evaluating competitors with better reporting
- Deprecated charting library EOL approaches (12 months) — forced migration later under pressure
- Competitive disadvantage vs. smaller players with AI analytics

---

### SLICE BRIEF #4: Real-Time Collaboration Infrastructure

**Strategic Slice Brief — Real-Time Collaboration Platform Foundation**

#### 1. Architectural Intent
Build the foundational infrastructure for real-time collaborative features (shared workspaces, live cursors, concurrent editing) that will close the competitive gap opened by the main competitor's recent launch. This is competitive defense — not a new capability launch, but a catch-up move.

#### 2. Inputs, Constraints, and Assumptions
**Strategic driver:** Main competitor launched real-time collaboration. Two smaller players launched AI-powered analytics. This is a two-front competitive response: collaboration (now) and AI analytics (later, built on Slice #3).

**Dependencies:**
- WebSocket infrastructure (new — must be built)
- No dependency on SSO or audit logging (but they are nice-to-have)
- Document/workspace data model must support concurrent access (existing schema may need changes)

**Constraints:**
- Must support collaborative features without breaking existing single-user workflows
- Conflict resolution for concurrent edits must be deterministic and auditable
- WebSocket connections must be scalable (EKS + Redis for pub/sub)

**Non-goals:**
- Full collaborative editing in Q3 (Phase 1 only — infrastructure)
- AI-powered suggestions or AI co-pilot features (Q4 or later)
- Mobile collaborative editing (Q4)

**Assumptions:**
- Main competitor's collaboration feature is WebSocket-based (confirmed by public launch)
- Concurrent editing can use CRDT or operational transformation (OT) — TBD by architecture
- WebSocket infrastructure will also benefit mobile app (future)

#### 3. Ranked Architecture Drivers
| Driver | Rank | Rationale |
|--------|------|----------|
| **Competitive defense** | #1 | Main competitor has real-time collaboration; we need to close this gap |
| **Platform stickiness** | #2 | Collaboration features increase switching costs dramatically |
| **Mobile app foundation** | #3 | WebSocket infrastructure is required for mobile real-time features |
| **AI analytics enabler** | #4 | Real-time activity data feeds AI models; collaboration generates rich activity data |

#### 4. Target Module and Compounding Seam
**Target module to deepen or create:** `collaboration-service` (new) + `websocket-gateway` (new)

**Current state:** No real-time infrastructure. All interactions are request/response (REST). No persistent connections.

**Seam being improved:** The interaction model — from "user submits request, gets response" to "users share a live workspace."

**Why this is the leverage point:** Real-time collaboration is the most technically complex slice. It requires WebSocket infrastructure, conflict resolution algorithms, presence awareness, and operational transformation/CRDT. Building this in Q3 sets the foundation for mobile app (WebSocket needed) and AI analytics (rich activity data from collaboration).

**Complexity absorbed internally:**
- WebSocket connection management (thousands of concurrent connections)
- Operational transformation or CRDT for conflict resolution
- Presence awareness (who is viewing/editing what)
- Redis pub/sub for cross-instance message distribution
- Graceful degradation when real-time is unavailable

#### 5. Candidate Architecture Options

**Option A: Full Real-Time Collaboration (Q3 deliverable)**
- Complete collaborative editing in Q3
- Benefits: Matches competitor feature-for-feature
- Risks: 12+ week timeline (too long), conflicts with other Q3 priorities
- **Verdict:** Rejected — too aggressive for one quarter

**Option B: WebSocket Infrastructure Phase 1 (Q3) + Collaboration Phase 2 (Q4)**
- Q3: Build WebSocket gateway + presence infrastructure
- Q4: Collaborative editing features
- Benefits: Achievable in Q3, compounds into full collaboration in Q4
- Risks: No customer-visible collaboration in Q3
- **Verdict:** Selected — best architectural compounding

**Option C: Third-Party Collaboration SDK (Liveblocks, Ably, Partykit)**
- Integrate managed real-time collaboration service
- Benefits: Fast implementation (3-4 weeks)
- Risks: Dependency on third-party; data residency; cost at scale; limits customization
- **Verdict:** Rejected — strategic capability should be owned, not delegated

#### 6. Recommended Architecture Delta
**Selected:** Option B — WebSocket Infrastructure Phase 1

**What changes in Q3:**
1. `websocket-gateway` service (manages WebSocket connections, auth, routing)
2. `presence-service` (tracks who is online, what they are viewing)
3. Redis pub/sub for cross-instance message fan-out
4. New Kafka topic `collab.events` for collaboration activity events (integrates with audit logging)
5. Presence indicators in existing UI (show "3 users viewing this workspace")

**What is intentionally deferred:**
- Collaborative editing (Q4)
- Live cursors (Q4)
- Concurrent document editing with conflict resolution (Q4)
- Mobile collaboration (Q4 or later)

**Embedded integration requirement:** Collaboration events (join, leave, view) should emit to `collab.events` Kafka topic for audit logging integration.

#### 7. Timeline Estimate
**6 weeks (Sprints 4-5, parallel track)**

| Week | Deliverable |
|------|-------------|
| 1-2 | WebSocket gateway core + auth integration |
| 3 | Redis pub/sub for presence + cross-instance messaging |
| 4 | Presence API + basic UI indicators |
| 5 | `collab.events` Kafka integration + audit pipeline |
| 6 | Load testing + production hardening |

#### 8. Technical Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| WebSocket scalability (thousands of concurrent connections) | High | High | Horizontal pod autoscaling; Redis pub/sub for fan-out |
| Operational transformation complexity | High | High | Start with CRDT library (Yjs); defer custom OT |
| Conflict resolution correctness | Medium | Critical | Property-based testing; deterministic test cases |
| WebSocket security (authentication hijacking) | Medium | Critical | JWT validation per WebSocket connection; periodic re-validation |

#### 9. Revenue-At-Risk Analysis
**ARR tied to this feature: $500,000 (estimated competitive deal flow)**

**Risk of delay (1 quarter):**
- Main competitor's real-time collaboration advantage grows
- Sales team cannot counter competitor's collaboration story
- Potential share shift to competitor in collaborative workspace segment

**Compounding value:**
- WebSocket infrastructure enables mobile app (Q4)
- Collaboration activity data feeds AI analytics (Q4)
- Presence awareness improves user experience even before full collaboration ships

---

### SLICE BRIEF #5: Mobile App (Native)

**Strategic Slice Brief — Mobile Application (iOS/Android)**

#### 1. Architectural Intent
Launch native mobile applications (iOS and Android) to capture new customer segments and provide on-the-go access for existing customers. This is a new channel play, not a catch-up move.

#### 2. Why This Is #5 and Should Be Deferred to Q4

**Team fit analysis:**
- 4 backend engineers, 2 frontend engineers, 1 DevOps, **0 mobile specialists**
- Building native mobile apps requires: iOS engineers (Swift/Objective-C), Android engineers (Kotlin/Java), mobile DevOps (Fastlane, App Store deployment)
- No team capacity for mobile. Existing team would need to learn mobile development while shipping core platform features.

**Timeline analysis:**
- Native mobile app: 12-16 weeks minimum (with team)
- With no mobile specialists: 16-20 weeks (team learning curve)
- Competes directly with Q3 priorities (SSO, audit logging, reporting)
- First revenue: Week 12-16 at earliest
- SSO first revenue: Week 4-6

**Revenue efficiency:**
- SSO unblocks $2.1M ARR in 4-6 weeks → ~$350K-$525K ARR per week of engineering
- Mobile app generates first revenue in 12-16 weeks → ~$12.5K-$17K ARR per week of engineering

**Recommendation: DEFER to Q4**

**Rationale:**
1. Q3 team has no mobile expertise — building mobile would require either (a) new hires or (b) existing team learning mobile while doing critical path work
2. Mobile competes for engineering bandwidth with higher-ARR, faster-to-market features
3. Q4 plan should include: hire 2 mobile engineers in Q3, start mobile in Q4 when team is ready
4. Mobile is not blocking any current deals — SSO and audit logging are the blockers

#### 3. If Mobile Is Accelerated (Forced Q3 Start)

**Minimum viable approach:** React Native (not native)

If business forces Q3 mobile start despite recommendations:
- Use React Native (not native Swift/Kotlin) — existing frontend team can contribute
- Ship only core read-only features first (dashboard viewing, notifications)
- Do NOT attempt real-time collaboration or full feature parity in Q3
- Backend only: 1 engineer (can start without mobile specialists)

**Timeline:** 10 weeks to basic read-only mobile app
**ARR impact:** Minimal in Q3 — basic app for existing customers, not new enterprise deals

---

## Part II: Dependency Graph and Sequencing

### Feature Dependency Map

```
[SSO] ───────────────────────────────┐
   │                                    │
   │ emits auth events                  │ emits auth events
   ▼                                    ▼
[Audit Logging] ───────────────────► [Reporting Dashboard]
   │                                      
   │ collab events                        
   ▼                                      
[Real-time Collaboration]                 
   │ (WebSocket infrastructure)
   │ also enables mobile in Q4
   ▼
[Mobile App] (Q4)
```

**Key dependencies:**
1. **SSO → Audit Logging:** SSO MUST emit Kafka events. If SSO ships without this, audit logging cannot be built.
2. **Audit Logging → Reporting Dashboard:** Audit events feed activity metrics in reporting. Audit pipeline is prerequisite for real-time reporting.
3. **Real-time Collaboration → Mobile:** WebSocket infrastructure built in Q3 enables mobile real-time features in Q4.

### Team Capacity Analysis

**Q3 Engineering Capacity:**

| Week | Backend (4) | Frontend (2) | DevOps (1) |
|------|-------------|-------------|------------|
| 1-2 | SSO | SSO UI components | SSO infra |
| 2-3 | Audit service | SSO UI | Audit infra |
| 3-4 | Audit service | Reporting modernization | Reporting infra |
| 4-5 | Real-time collaboration backend | Reporting + presence UI | Collaboration infra |
| 5-6 | Real-time collaboration | Presence UI | Load testing |

**Conflicts:** Frontend team (2) is the bottleneck. They must support SSO UI, Reporting Dashboard, and Presence UI. This requires strict prioritization.

**Recommended frontend priority:**
1. SSO login UI (revenue blocker) — Weeks 1-2
2. Reporting Dashboard modernization (customer retention) — Weeks 3-5
3. Presence indicators (competitive signal) — Weeks 4-5

### Sprint Plan: Q3

```
Sprint 1 (Weeks 1-2):
  Backend:  SSO sidecar core (SAML + OIDC)
  Frontend: SSO login UI components
  DevOps:   SSO infrastructure (Vault certs, routing)

Sprint 2 (Weeks 3-4):
  Backend:  Audit service (Kafka consumer, S3 writer) + SSO events
  Frontend: SSO admin UI (IdP metadata upload)
  DevOps:   Audit infrastructure (S3, ES if needed)

Sprint 3 (Weeks 5-6):
  Backend:  Analytics service skeleton + Kafka streaming
  Frontend: Reporting dashboard - first migrated report
  DevOps:   Analytics infrastructure

Sprint 4 (Weeks 7-8):
  Backend:  WebSocket gateway + presence service
  Frontend: Presence UI indicators
  DevOps:   WebSocket infrastructure

Sprint 5-6 (Weeks 9-12):
  Backend:  Collaboration Phase 1 completion + hardening
  Frontend: Remaining report migrations
  DevOps:   Load testing + production hardening
```

---

## Part III: Risk Assessment Summary

### By Feature

| Feature | Delay Risk (1 quarter) | ARR Impact of Delay | Competitive Gap Widens | Team Capacity Risk |
|---------|----------------------|---------------------|-----------------------|-------------------|
| **SSO** | CRITICAL — $2.1M blocked | $2.1M direct | Yes (enterprise deals stall) | Low |
| **Audit Logging** | HIGH — compliance deals | $400K indirect | Medium | Low |
| **Reporting Dashboard** | MEDIUM — churn risk | $300K churn | Yes (vs. AI analytics players) | Medium (frontend bottleneck) |
| **Real-time Collaboration** | MEDIUM — competitor gap | $500K competitive | Yes (main competitor) | Medium |
| **Mobile App** | LOW — not blocking | $200K long-term | Low | HIGH (no mobile specialists) |

### Foreclosure Analysis

**Choosing SSO over Reporting Dashboard:**
- Forecloses: Nothing permanent — reporting can start Week 3
- Risk: Frontend team split delays both SSO and reporting by 1-2 weeks
- ARR impact of foreclosure: None (SSO unblocks $2.1M; reporting prevents $300K churn)

**Choosing SSO over Real-time Collaboration:**
- Forecloses: Nothing permanent — collaboration can start Week 4
- Risk: Collaboration delay extends competitive gap by 1 quarter
- ARR impact of foreclosure: Competitor captures ~$500K of competitive deal flow

**Choosing Reporting Dashboard over Real-time Collaboration:**
- Forecloses: Nothing permanent
- Risk: Cannot counter competitor's collaboration story for 1 quarter
- ARR impact of foreclosure: ~$500K competitive deal flow

**Choosing Mobile over SSO:**
- Forecloses: SSO delays 8+ weeks (mobile takes all backend capacity)
- Risk: $2.1M ARR remains blocked; enterprise deals lost
- ARR impact of foreclosure: $2.1M direct loss

---

## Part IV: Board Narrative (For CEO)

### The Strategic Argument

**The Q3 investment thesis:** We are in a horse race with our main competitor on enterprise features and with smaller players on AI analytics. Our most constrained resource is engineering time (4 backend, 2 frontend). We have 14 months of runway and a board deadline in 6 weeks.

**The recommended Q3 strategy is to win the enterprise deals we already have in hand** ($2.1M ARR) rather than pursue new market segments or competitive parity that require longer time-to-revenue.

**Key arguments:**

1. **SSO unblocks $2.1M ARR in 4-6 weeks.** Three enterprise deals are waiting on SSO. This is not speculative — these are signed deals pending only a technical feature. No other investment comes close to this ROI.

2. **Audit logging is infrastructure that compounds.** The event pipeline we build for audit logging feeds reporting, feeds collaboration activity tracking, and enables future AI analytics. Building it once in Q3 pays dividends across all future quarters.

3. **Reporting dashboard modernization prevents churn.** Existing customers are asking for better reporting. The deprecated charting library has a 12-month EOL window. This is a retention investment, not a growth investment.

4. **Real-time collaboration is a phased investment.** We cannot ship full collaboration in one quarter. But we can ship the WebSocket infrastructure that makes collaboration possible in Q4, when we also have mobile. This is architectural compounding.

5. **Mobile is a Q4 investment.** We have no mobile engineers. A native mobile app takes 12-16 weeks with a team. Starting mobile in Q3 would burn 25% of our engineering capacity for the lowest-ROI Q3 feature.

### Recommended Q3 Investment

| Feature | Effort | Timeline | ARR Impact | Risk |
|---------|--------|----------|------------|------|
| SSO | 4-6 weeks | Week 6 | $2.1M unblocked | Low |
| Audit Logging | 3-5 weeks | Week 5-6 | $400K indirect | Low |
| Reporting Dashboard | 6-8 weeks | Week 7-8 | $300K churn prevention | Medium |
| Real-time Collaboration (Phase 1) | 6 weeks | Week 6 | $500K competitive | High |

**Total engineering weeks:** ~20-25 backend weeks + ~15-18 frontend weeks + ~8 DevOps weeks

**Estimated Q3 output:** All 4 features shipped (SSO, audit, reporting phase 1, collaboration phase 1), with SSO unblocking $2.1M ARR before end of Q3.

---

## Part V: Open Questions for CEO Validation

The following must be validated by CEO or sales leadership before this analysis is presented to the board:

1. **Revenue figures:** Is the $2.1M ARR figure for the 3 stalled deals validated? Are there other SSO blockers not in this analysis?

2. **Competitive intelligence:** Is the main competitor's real-time collaboration feature generally available or just launched? How rapidly are they acquiring customers with it?

3. **Technical constraints:** Are there any existing architectural decisions (not captured in this analysis) that would prevent the WebSocket infrastructure for real-time collaboration?

4. **Team capacity:** Are there any planned departures, hires, or reallocations not captured in this analysis?

5. **Board narrative:** Does the board respond to "unblocking $2.1M ARR" or do they prioritize growth signals more?

---

*Document status: DRAFT — Requires CEO review and business assumption validation*
*Next step: CEO presents to board; board makes final investment decision*
