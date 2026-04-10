import type { Knex } from 'knex';

/**
 * Migration: 001_delivery_channels
 * 
 * Creates the delivery_channels table to enumerate supported notification
 * delivery mechanisms. This table is extensible - new channels can be added
 * via INSERT without schema migration by using the 'custom' channel_type
 * with channel-specific configuration in the config JSONB column.
 * 
 * Design decisions:
 * - channel_type enum restricts built-in types for data integrity
 * - config JSONB allows channel-specific settings without schema changes
 * - priority_weight enables delivery ordering when multiple channels are active
 * - is_active allows soft-disable of channels without deletion
 * - UNIQUE(name) prevents duplicate channel registration
 * - Index on channel_type for filtering by channel family
 */
export async function up(knex: Knex): Promise<void> {
  await knex.schema.createTable('delivery_channels', (table) => {
    // Primary key - UUID for distributed system compatibility
    table.uuid('id').primary().defaultTo(knex.raw('gen_random_uuid()'));

    // Channel identification
    table.string('name', 100).notNullable().unique();
    table.string('description', 500);
    
    // Channel type enum - restricts built-in types for referential integrity
    // Using enum for built-in types, 'custom' for extensible channels
    table.enum('channel_type', [
      'email',
      'push',
      'in_app',
      'sms',
      'slack',
      'teams',
      'webhook',
      'custom'
    ]).notNullable().defaultTo('custom');
    
    // Channel-specific configuration stored as JSONB
    // Examples:
    // - email: { smtp_host, smtp_port, from_address, from_name }
    // - push: { fcm_project_id, apns_topic }
    // - webhook: { url_template, headers, timeout_ms, retry_policy }
    // - custom: { adapter_name, adapter_config }
    table.jsonb('config').notNullable().defaultTo('{}');
    
    // Delivery characteristics
    table.integer('priority_weight').notNullable().defaultTo(1);
    table.boolean('is_active').notNullable().defaultTo(true);
    
    // Capabilities flags for delivery requirements
    table.boolean('supports_batching').notNullable().defaultTo(false);
    table.boolean('supports_digest').notNullable().defaultTo(false);
    table.boolean('supports_rich_content').notNullable().defaultTo(false);
    table.integer('max_payload_size_bytes').nullable(); // null = unlimited
    
    // Templates for this channel (can be overridden per notification type)
    table.uuid('default_template_id').nullable();
    
    // Audit timestamps
    table.timestamp('created_at', { useTz: true }).notNullable().defaultTo(knex.fn.now());
    table.timestamp('updated_at', { useTz: true }).notNullable().defaultTo(knex.fn.now());
    
    // Indexes
    table.index('channel_type');
    table.index('is_active');
    table.index(['channel_type', 'is_active'], 'idx_channels_type_active');
  });
}

export async function down(knex: Knex): Promise<void> {
  await knex.schema.dropTableIfExists('delivery_channels');
}
