/**
 * Delivery Channel Model
 * 
 * Represents a notification delivery channel (email, push, SMS, etc.)
 * in the database.
 */

import { Model, QueryBuilder } from 'objection';
import { z } from 'zod';

// Channel type enum matching the database enum
export const ChannelType = [
  'email',
  'push',
  'in_app',
  'sms',
  'slack',
  'teams',
  'webhook',
  'custom',
] as const;

export type ChannelTypeValue = typeof ChannelType[number];

// Zod schema for channel creation
export const DeliveryChannelCreateSchema = z.object({
  name: z.string().max(100),
  description: z.string().max(500).nullable().optional(),
  channelType: z.enum(ChannelType).default('custom'),
  config: z.record(z.unknown()).default({}),
  priorityWeight: z.number().int().min(0).default(1),
  isActive: z.boolean().default(true),
  supportsBatching: z.boolean().default(false),
  supportsDigest: z.boolean().default(false),
  supportsRichContent: z.boolean().default(false),
  maxPayloadSizeBytes: z.number().int().nullable().optional(),
  defaultTemplateId: z.string().uuid().nullable().optional(),
});

export const DeliveryChannelUpdateSchema = DeliveryChannelCreateSchema.partial();

export type DeliveryChannelCreateInput = z.infer<typeof DeliveryChannelCreateSchema>;
export type DeliveryChannelUpdateInput = z.infer<typeof DeliveryChannelUpdateSchema>;

// Database model class
export class DeliveryChannel extends Model {
  static tableName = 'delivery_channels';

  // Columns
  id!: string;
  name!: string;
  description!: string | null;
  channelType!: ChannelTypeValue;
  config!: Record<string, unknown>;
  priorityWeight!: number;
  isActive!: boolean;
  supportsBatching!: boolean;
  supportsDigest!: boolean;
  supportsRichContent!: boolean;
  maxPayloadSizeBytes!: number | null;
  defaultTemplateId!: string | null;
  createdAt!: Date;
  updatedAt!: Date;

  // Relationships
  static relationMappings = {
    defaultTemplate: {
      relation: Model.BelongsToOneRelation,
      modelClass: () => NotificationTemplate,
      join: {
        from: 'delivery_channels.default_template_id',
        to: 'notification_templates.id',
      },
    },
    userPreferences: {
      relation: Model.HasManyRelation,
      modelClass: () => UserNotificationPreference,
      join: {
        from: 'delivery_channels.id',
        to: 'user_notification_preferences.channel_id',
      },
    },
    deliveryLogs: {
      relation: Model.HasManyRelation,
      modelClass: () => NotificationDeliveryLog,
      join: {
        from: 'delivery_channels.id',
        to: 'notification_delivery_log.channel_id',
      },
    },
  };

  // Query scopes
  static queryScopes = {
    active() {
      return (builder: QueryBuilder<DeliveryChannel>) => {
        builder.where('is_active', true);
      };
    },
    byType(channelType: ChannelTypeValue) {
      return (builder: QueryBuilder<DeliveryChannel>) => {
        builder.where('channel_type', channelType);
      };
    },
    supportsDigest() {
      return (builder: QueryBuilder<DeliveryChannel>) => {
        builder.where('supports_digest', true).where('is_active', true);
      };
    },
    orderedByPriority() {
      return (builder: QueryBuilder<DeliveryChannel>) => {
        builder.where('is_active', true).orderBy('priority_weight', 'desc');
      };
    },
  };

  // Timestamps
  $beforeInsert() {
    this.createdAt = new Date();
    this.updatedAt = new Date();
  }

  $beforeUpdate() {
    this.updatedAt = new Date();
  }
}

// Forward declarations
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import type { NotificationTemplate } from './notification-template';
import type { UserNotificationPreference } from './notification-preference';
import type { NotificationDeliveryLog } from './notification-delivery-log';

export default DeliveryChannel;
