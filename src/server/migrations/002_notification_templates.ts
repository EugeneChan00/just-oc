import type { Knex } from 'knex';

/**
 * Migration: 002_notification_templates
 * 
 * Creates the notification_templates table for storing Handlebars templates
 * used to render notification content. Supports template versioning,
 * variable interpolation, and channel-specific overrides.
 * 
 * Design decisions:
 * - Templates are channel-agnostic by default; channel_override provides
 *   channel-specific template content
 * - handlebars_variables JSONB stores metadata about required template variables
 *   for validation and documentation without parsing the template
 * - Version support via versioning_key (e.g., "welcome_email_v2") and is_active flag
 * - UNIQUE(name, version) ensures version uniqueness per template family
 * - Indexes support lookup by name (for latest version queries) and
 *   by notification_type (for routing-based lookups)
 * 
 * Fan-out consideration: Templates are shared across all users, not copied
 * per-recipient. Variable interpolation happens at render time with user-specific
 * data passed from the notifications record and user profile.
 */
export async function up(knex: Knex): Promise<void> {
  await knex.schema.createTable('notification_templates', (table) => {
    // Primary key
    table.uuid('id').primary().defaultTo(knex.raw('gen_random_uuid()'));

    // Template identification and versioning
    table.string('name', 100).notNullable();
    table.string('version', 50).notNullable().defaultTo('v1');
    table.string('notification_type', 100).notNullable(); // e.g., "order_confirmation", "password_reset"
    
    // Template content
    table.text('subject_template').notNullable(); // Handlebars: "Hello {{user.name}}!"
    table.text('body_template').notNullable();     // Handlebars HTML or plain text
    table.text('short_body_template').nullable();  // For push notifications, SMS, etc.
    
    // Channel-specific overrides (keyed by channel_type from delivery_channels)
    // Stored as JSONB: { "email": { subject_override, body_override }, "push": {...} }
    table.jsonb('channel_overrides').notNullable().defaultTo('{}');
    
    // Template metadata for validation and documentation
    table.jsonb('handlebars_variables').notNullable().defaultTo('[]');
    // Example: ["user.name", "user.email", "order.number", "order.total"]
    
    // Template configuration
    table.boolean('is_active').notNullable().defaultTo(true);
    table.string('description', 500).nullable();
    
    // Priority for rendering order when multiple templates match
    table.integer('priority').notNullable().defaultTo(0);
    
    // Audit timestamps
    table.timestamp('created_at', { useTz: true }).notNullable().defaultTo(knex.fn.now());
    table.timestamp('updated_at', { useTz: true }).notNullable().defaultTo(knex.fn.now());
    
    // Unique constraint on name + version
    table.unique(['name', 'version']);
    
    // Indexes for common query patterns
    table.index('notification_type');
    table.index('name');
    table.index(['notification_type', 'is_active'], 'idx_templates_type_active');
    table.index(['name', 'is_active'], 'idx_templates_name_active');
  });
}

export async function down(knex: Knex): Promise<void> {
  await knex.schema.dropTableIfExists('notification_templates');
}
