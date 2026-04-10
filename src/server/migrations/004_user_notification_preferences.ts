import type { Knex } from 'knex';

/**
 * Migration: 004_user_notification_preferences
 * 
 * Creates the user_notification_preferences table for storing per-user,
 * per-channel notification preferences. Supports opt-in/opt-out per channel,
 * digest mode configuration, and quiet hours.
 * 
 * Design decisions:
 * - Each row represents a user's preference for a specific channel
 * - Default preferences are created when a user explicitly sets any preference
 * - The system should initialize default preferences for new users from
 *   system-wide defaults (handled in application code, not schema)
 * 
 * - Opt-in model: is_enabled = true means the user has opted IN to receive
 *   notifications on this channel. Some channels may default to enabled
 *   (transactional: order confirmations) while others default to disabled
 *   (marketing, promotional).
 * 
 * - Digest mode: When the user prefers digest delivery:
 *     - delivery_mode = 'real_time': Immediate delivery regardless
 *     - delivery_mode = 'hourly': Accumulate and send hourly digest
 *     - delivery_mode = 'daily': Accumulate and send daily digest at digest_time
 *   The notification's batch_mode also plays a role - notifications marked
 *   batch_mode='none' always go real-time even if user prefers digest.
 * 
 * - Quiet hours: quiet_hours_start and quiet_hours_end define a window
 *   during which non-critical notifications are held. critical priority
 *   notifications bypass quiet hours.
 * 
 * - UNIQUE(user_id, channel_id) ensures one preference row per user per channel
 * - INDEX idx_preferences_user_channel covers the lookup pattern
 * - INDEX idx_preferences_channel_enabled supports channel-wide broadcast queries
 */
export async function up(knex: Knex): Promise<void> {
  await knex.schema.createTable('user_notification_preferences', (table) => {
    // Primary key
    table.uuid('id').primary().defaultTo(knex.raw('gen_random_uuid()'));

    // User reference
    table.uuid('user_id').notNullable()
      .comment('References users.id');
    
    // Channel reference
    table.uuid('channel_id').notNullable()
      .comment('References delivery_channels.id');
    
    // Opt-in/opt-out for this channel
    table.boolean('is_enabled').notNullable().defaultTo(true)
      .comment('True = opted in to receive notifications on this channel');
    
    // Delivery mode preference
    table.enum('delivery_mode', ['real_time', 'hourly', 'daily'])
      .notNullable().defaultTo('real_time')
      .comment('How to deliver notifications on this channel');
    
    // Digest delivery time preference (for daily digest)
    // Stored as local time offset from UTC, e.g., -5 for EST
    table.string('digest_timezone', 50).nullable().defaultTo('UTC')
      .comment('IANA timezone for digest delivery, e.g., America/New_York');
    table.time('digest_time', { useTz: false }).nullable()
      .comment('Local time to send daily digest, e.g., 09:00:00');
    
    // Quiet hours (non-critical notifications held during this window)
    table.boolean('quiet_hours_enabled').notNullable().defaultTo(false);
    table.time('quiet_hours_start', { useTz: false }).nullable();
    table.time('quiet_hours_end', { useTz: false }).nullable();
    table.string('quiet_hours_timezone', 50).nullable().defaultTo('UTC')
      .comment('IANA timezone for quiet hours interpretation');
    
    // Notification type filters (opt-out specific types on this channel)
    table.jsonb('disabled_notification_types').notNullable().defaultTo('[]')
      .comment('Array of notification_type strings the user has disabled on this channel');
    
    // Metadata
    table.string('description', 500).nullable();
    
    // Audit timestamps
    table.timestamp('created_at', { useTz: true }).notNullable().defaultTo(knex.fn.now());
    table.timestamp('updated_at', { useTz: true }).notNullable().defaultTo(knex.fn.now());
    
    // Foreign key constraints
    table.foreign('user_id').references('id').inTable('users').onDelete('CASCADE');
    table.foreign('channel_id').references('id').inTable('delivery_channels').onDelete('CASCADE');
    
    // Unique constraint - one preference per user per channel
    table.unique(['user_id', 'channel_id']);
    
    // Indexes
    table.index('user_id');
    table.index('channel_id');
    table.index(['user_id', 'channel_id'], 'idx_preferences_user_channel');
    table.index(['channel_id', 'is_enabled'], 'idx_preferences_channel_enabled');
  });
}

export async function down(knex: Knex): Promise<void> {
  await knex.schema.dropTableIfExists('user_notification_preferences');
}
