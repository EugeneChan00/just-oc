import type { Knex } from 'knex';

/**
 * Migration: 003_notifications
 * 
 * Creates the core notifications table. This is the highest-volume table
 * expected to handle 10M+ rows/day at steady state.
 * 
 * Design decisions:
 * - Partitioning: This table SHOULD be partitioned by created_at (RANGE)
 *   using PostgreSQL's declarative partitioning. A follow-up migration should
 *   create partitions (e.g., daily or weekly) for data lifecycle management.
 *   At 10M/day, consider weekly partitions initially with daily if needed.
 * 
 * - Fan-out handling: For broadcast notifications (single notification to
 *   many recipients), we use:
 *     1. is_broadcast = true: single row representing the broadcast intent
 *     2. broadcast_scope: 'all_users' | 'segment_<id>' | 'explicit_list'
 *     3. The delivery_log materialized per-recipient serves as the actual
 *        recipient list for broadcast queries
 *   This avoids storing N identical copies of the same notification.
 * 
 * - TTL/Expiration: expires_at column allows per-notification-type TTL
 *   configuration. Default TTL varies by notification type:
 *     - critical: 90 days (security, billing)
 *     - high: 30 days (orders, shipping)
 *     - normal: 7 days (marketing, promotions)
 *     - low: 24 hours (social, activity)
 *   Expiration enforcement via pg_cron job (see rationale document).
 * 
 * - Priority levels determine:
 *     1. Delivery order (critical first)
 *     2. Retry behavior (critical = infinite retry with backoff)
 *     3. Queue placement (separate queues per priority)
 * 
 * - Composite index (user_id, is_read, created_at) supports the primary
 *   read path: "notification inbox" sorted by recency with read/unread filter.
 * 
 * - INDEX idx_notifications_user_unread_created: Covers the notification
 *   inbox query with all columns needed (no covering index needed for
 *   simple select, but see composite below).
 * 
 * - INDEX idx_notifications_user_priority_created: Supports inbox sorting
 *   by priority within time window.
 */
export async function up(knex: Knex): Promise<void> {
  await knex.schema.createTable('notifications', (table) => {
    // Primary key
    table.uuid('id').primary().defaultTo(knex.raw('gen_random_uuid()'));

    // Recipient (single recipient for direct, null for broadcast)
    table.uuid('user_id').nullable()
      .comment('Null for broadcast notifications; for direct notifications, references users.id');
    
    // Notification classification
    table.string('notification_type', 100).notNullable()
      .comment('Categorization for routing and preference matching, e.g., order_confirmation');
    table.string('event_type', 100).notNullable()
      .comment('Specific event that triggered this notification, e.g., order_shipped');
    
    // Template reference for content rendering
    table.uuid('template_id').nullable()
      .comment('References notification_templates.id; can be overridden per-channel');
    
    // Rendered content (pre-computed for performance at high volume)
    // Store pre-rendered subject and body to avoid template compilation on read
    table.text('subject').nullable();
    table.text('body').nullable();
    table.jsonb('rendered_content').nullable()
      .comment('Pre-rendered content per channel: { "email": {...}, "push": {...} }');
    
    // Priority classification (determines delivery order and retry behavior)
    table.enum('priority', ['critical', 'high', 'normal', 'low'])
      .notNullable().defaultTo('normal');
    
    // Broadcast flag for fan-out notifications
    table.boolean('is_broadcast').notNullable().defaultTo(false);
    table.string('broadcast_scope', 100).nullable()
      .comment('For broadcasts: all_users, segment_<id>, or explicit_list');
    table.jsonb('broadcast_recipient_ids').nullable()
      .comment('For explicit_list scope: array of user UUIDs');
    
    // Payload for dynamic variables not pre-rendered
    table.jsonb('payload').notNullable().defaultTo('{}')
      .comment('Variable data passed to template renderer: { order_id, tracking_number, ... }');
    
    // Delivery configuration
    table.boolean('is_immediate').notNullable().defaultTo(true)
      .comment('If false, notification is queued for batch/digest processing');
    table.enum('batch_mode', ['none', 'hourly', 'daily']).notNullable().defaultTo('none')
      .comment('Digest mode overrides is_immediate when user preference is digest');
    
    // Read status tracking
    table.boolean('is_read').notNullable().defaultTo(false);
    table.timestamp('read_at', { useTz: true }).nullable();
    
    // Soft delete for recovery (hard delete should be rare)
    table.boolean('is_deleted').notNullable().defaultTo(false);
    table.timestamp('deleted_at', { useTz: true }).nullable();
    
    // TTL/Expiration
    table.timestamp('expires_at', { useTz: true }).nullable()
      .comment('UTC timestamp when this notification expires; NULL = never expires');
    
    // Audit timestamps
    table.timestamp('created_at', { useTz: true }).notNullable().defaultTo(knex.fn.now());
    table.timestamp('updated_at', { useTz: true }).notNullable().defaultTo(knex.fn.now());
    
    // Foreign key constraints
    table.foreign('user_id').references('id').inTable('users').onDelete('SET NULL');
    table.foreign('template_id').references('id').inTable('notification_templates').onDelete('SET NULL');
    
    // Check constraints
    table.check('??', ['is_broadcast = true OR user_id IS NOT NULL'],
      ['user_id_or_broadcast_check'],
      'Broadcast notifications must not have a user_id, direct notifications must have one');
    
    // Indexes for common query patterns
    
    // PRIMARY INBOX QUERY: user notifications sorted by created_at
    // This composite index covers the most frequent read path
    table.index(['user_id', 'is_read', 'created_at'], 'idx_notifications_inbox');
    
    // Fallback/index for users without specific preferences
    table.index(['user_id', 'created_at'], 'idx_notifications_user_created');
    
    // Priority-based delivery ordering for worker polling
    table.index(['priority', 'is_read', 'created_at'], 'idx_notifications_priority_delivery');
    
    // Broadcast queries (find all broadcasts for fan-out)
    table.index(['is_broadcast', 'created_at'], 'idx_notifications_broadcast');
    
    // Expiration cleanup queries
    table.index(['expires_at', 'is_deleted'], 'idx_notifications_expiration');
    
    // Template lookup for rendering
    table.index('template_id');
    
    // Notification type queries (for analytics, preference matching)
    table.index('notification_type');
    
    // Composite index for user + priority sorting (inbox with priority grouping)
    table.index(['user_id', 'priority', 'created_at'], 'idx_notifications_user_priority_created');
  });
}

export async function down(knex: Knex): Promise<void> {
  await knex.schema.dropTableIfExists('notifications');
}
