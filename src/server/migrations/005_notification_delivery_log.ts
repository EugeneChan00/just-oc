import type { Knex } from 'knex';

/**
 * Migration: 005_notification_delivery_log
 * 
 * Creates the notification_delivery_log table for tracking individual
 * delivery attempts per notification per channel. This is the primary
 * table for broadcast fan-out - each recipient of a broadcast notification
 * gets their own delivery_log row.
 * 
 * Design decisions:
 * - This table has the highest write volume (one row per notification per channel
 *   per recipient, potentially 10M+ rows/day)
 * - Consider partitioning by created_at (like notifications table) for
 *   efficient expiration and archival
 * 
 * - Fan-out via delivery_log: When a broadcast notification is created:
 *     1. A single row in notifications with is_broadcast=true
 *     2. Delivery workers query notifications WHERE is_broadcast=true AND
 *        created_at > last_processed_at
 *     3. For each recipient in the broadcast scope, a delivery_log row
 *        is created with status='pending'
 *     4. Workers process delivery_log rows, updating status
 *   This approach means broadcast notifications are "materialized" into
 *   individual delivery records at delivery time, allowing per-recipient
 *   tracking and retry without duplicating notification content.
 * 
 * - Status state machine:
 *     pending -> sent | failed
 *     sent -> delivered | failed (permanent failure after max retries)
 *     delivered -> read (when read receipt received)
 *     failed -> pending (for retry if retryable)
 * 
 * - delivery_attempt tracks retry count. After max_attempts is reached,
 *   status becomes 'failed' and no further automatic retries occur.
 * 
 * - delivered_at captures when the notification was successfully delivered
 *   to the channel (e.g., SMTP server accepted, FCM delivered)
 * 
 * - read_at captures when the user actually viewed/read the notification.
 *   For push and in-app, this comes from client-side read receipt.
 *   For email, this can be approximated via open tracking pixels (if enabled).
 * 
 * - rendered_content stores the final rendered content for this specific
 *   delivery attempt, allowing per-recipient variable substitution to be
 *   preserved even if the template is later updated.
 * 
 * - INDEX idx_delivery_log_notification_channel: Unique constraint ensures
 *   one delivery attempt record per notification per channel per recipient.
 * 
 * - INDEX idx_delivery_log_user_inbox: Supports "unread count" and
 *   "inbox list" queries for the user's notification center.
 * 
 * - INDEX idx_delivery_log_pending: Supports worker polling for
 *   pending deliveries with priority ordering.
 * 
 * - INDEX idx_delivery_log_expiration: Supports cleanup of old delivery
 *   logs (may have different retention than notifications themselves).
 */
export async function up(knex: Knex): Promise<void> {
  await knex.schema.createTable('notification_delivery_log', (table) => {
    // Primary key
    table.uuid('id').primary().defaultTo(knex.raw('gen_random_uuid()'));

    // Notification reference
    table.uuid('notification_id').notNullable()
      .comment('References notifications.id');
    
    // Recipient reference (denormalized for query performance)
    table.uuid('user_id').notNullable()
      .comment('References users.id - denormalized from notifications for inbox queries');
    
    // Channel reference
    table.uuid('channel_id').notNullable()
      .comment('References delivery_channels.id');
    
    // Delivery status tracking
    table.enum('status', [
      'pending',
      'sent',
      'delivered',
      'read',
      'failed',
      'cancelled'
    ]).notNullable().defaultTo('pending');
    
    // Rendered content snapshot (preserved at delivery time)
    table.text('rendered_subject').nullable();
    table.text('rendered_body').nullable();
    table.jsonb('rendered_metadata').nullable()
      .comment('Channel-specific delivery metadata, e.g., email_message_id, fcm_message_id');
    
    // Delivery attempt tracking
    table.integer('attempt_count').notNullable().defaultTo(0);
    table.integer('max_attempts').notNullable().defaultTo(3);
    table.timestamp('last_attempt_at', { useTz: true }).nullable();
    table.text('last_error').nullable()
      .comment('Last error message if delivery failed');
    
    // Timing
    table.timestamp('sent_at', { useTz: true }).nullable()
      .comment('When notification was handed to channel (e.g., SMTP accepted)');
    table.timestamp('delivered_at', { useTz: true }).nullable()
      .comment('When channel confirmed delivery (e.g., FCM delivered)');
    table.timestamp('read_at', { useTz: true }).nullable()
      .comment('When user viewed/read the notification');
    
    // Read receipt tracking
    table.jsonb('read_receipt_metadata').nullable()
      .comment('Channel-specific read receipt data, e.g., email_open_timestamp');
    
    // Digest batch assignment
    table.uuid('digest_batch_id').nullable()
      .comment('For digest-mode notifications, groups related notifications in one delivery');
    table.integer('digest_position').nullable()
      .comment('Order within the digest batch');
    
    // Soft delete for recovery
    table.boolean('is_deleted').notNullable().defaultTo(false);
    
    // Audit timestamps
    table.timestamp('created_at', { useTz: true }).notNullable().defaultTo(knex.fn.now());
    table.timestamp('updated_at', { useTz: true }).notNullable().defaultTo(knex.fn.now());
    
    // Foreign key constraints
    table.foreign('notification_id').references('id').inTable('notifications').onDelete('CASCADE');
    table.foreign('user_id').references('id').inTable('users').onDelete('CASCADE');
    table.foreign('channel_id').references('id').inTable('delivery_channels').onDelete('CASCADE');
    
    // Unique constraint - one delivery log per notification per channel per user
    table.unique(['notification_id', 'channel_id', 'user_id'], 'idx_delivery_log_unique');
    
    // Indexes
    
    // PRIMARY READ PATH: User inbox query
    // SELECT * FROM notification_delivery_log WHERE user_id = ? AND status != 'cancelled' ORDER BY created_at DESC
    table.index(['user_id', 'status', 'created_at'], 'idx_delivery_log_user_inbox');
    
    // Unread count query: COUNT(*) WHERE user_id = ? AND status NOT IN ('read', 'cancelled')
    table.index(['user_id', 'status'], 'idx_delivery_log_user_unread_count');
    
    // Worker polling: find pending deliveries ordered by priority and created_at
    table.index(['status', 'created_at'], 'idx_delivery_log_pending');
    
    // Retry processing: find failed deliveries eligible for retry
    table.index(['status', 'attempt_count', 'last_attempt_at'], 'idx_delivery_log_retry');
    
    // Notification lookup for status updates
    table.index('notification_id');
    
    // Digest batch lookup
    table.index('digest_batch_id');
    
    // Expiration/cleanup
    table.index(['created_at', 'is_deleted'], 'idx_delivery_log_expiration');
    
    // Channel performance analytics
    table.index(['channel_id', 'status', 'created_at'], 'idx_delivery_log_channel_stats');
  });
}

export async function down(knex: Knex): Promise<void> {
  await knex.schema.dropTableIfExists('notification_delivery_log');
}
