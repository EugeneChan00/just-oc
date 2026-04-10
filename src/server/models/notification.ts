/**
 * Notification Model
 * 
 * Represents the core notification entity in the database.
 * This is the highest-volume table in the system.
 */

import { Model, QueryBuilder } from 'objection';
import { z } from 'zod';

// Enum schemas for runtime validation
export const NotificationPriority = ['critical', 'high', 'normal', 'low'] as const;
export const NotificationBatchMode = ['none', 'hourly', 'daily'] as const;
export const BroadcastScope = ['all_users', 'segment', 'explicit_list'] as const;

export type NotificationPriorityType = typeof NotificationPriority[number];
export type NotificationBatchModeType = typeof NotificationBatchMode[number];
export type BroadcastScopeType = typeof BroadcastScope[number];

// Zod schema for notification creation
export const NotificationCreateSchema = z.object({
  userId: z.string().uuid().nullable(),
  notificationType: z.string().max(100),
  eventType: z.string().max(100),
  templateId: z.string().uuid().nullable().optional(),
  subject: z.string().max(500).nullable().optional(),
  body: z.string().nullable().optional(),
  renderedContent: z.record(z.unknown()).nullable().optional(),
  priority: z.enum(NotificationPriority).default('normal'),
  isBroadcast: z.boolean().default(false),
  broadcastScope: z.enum(BroadcastScope).nullable().optional(),
  broadcastRecipientIds: z.array(z.string().uuid()).nullable().optional(),
  payload: z.record(z.unknown()).default({}),
  isImmediate: z.boolean().default(true),
  batchMode: z.enum(NotificationBatchMode).default('none'),
  expiresAt: z.date().nullable().optional(),
});

export const NotificationUpdateSchema = NotificationCreateSchema.partial();

export type NotificationCreateInput = z.infer<typeof NotificationCreateSchema>;
export type NotificationUpdateInput = z.infer<typeof NotificationUpdateSchema>;

// Database model class
export class Notification extends Model {
  static tableName = 'notifications';

  // Columns
  id!: string;
  userId!: string | null;
  notificationType!: string;
  eventType!: string;
  templateId!: string | null;
  subject!: string | null;
  body!: string | null;
  renderedContent!: Record<string, unknown> | null;
  priority!: NotificationPriorityType;
  isBroadcast!: boolean;
  broadcastScope!: BroadcastScopeType | null;
  broadcastRecipientIds!: string[] | null;
  payload!: Record<string, unknown>;
  isImmediate!: boolean;
  batchMode!: NotificationBatchModeType;
  isRead!: boolean;
  readAt!: Date | null;
  isDeleted!: boolean;
  deletedAt!: Date | null;
  expiresAt!: Date | null;
  createdAt!: Date;
  updatedAt!: Date;

  // Relationships
  static relationMappings = {
    user: {
      relation: Model.BelongsToOneRelation,
      modelClass: () => User,
      join: {
        from: 'notifications.user_id',
        to: 'users.id',
      },
    },
    template: {
      relation: Model.BelongsToOneRelation,
      modelClass: () => NotificationTemplate,
      join: {
        from: 'notifications.template_id',
        to: 'notification_templates.id',
      },
    },
    deliveryLogs: {
      relation: Model.HasManyRelation,
      modelClass: () => NotificationDeliveryLog,
      join: {
        from: 'notifications.id',
        to: 'notification_delivery_log.notification_id',
      },
    },
  };

  // Query scopes
  static queryScopes = {
    inbox(userId: string) {
      return (builder: QueryBuilder<Notification>) => {
        builder
          .where('user_id', userId)
          .where('is_deleted', false)
          .orderBy('created_at', 'desc');
      };
    },
    unread(userId: string) {
      return (builder: QueryBuilder<Notification>) => {
        builder
          .where('user_id', userId)
          .where('is_read', false)
          .where('is_deleted', false)
          .orderBy('created_at', 'desc');
      };
    },
    pendingDelivery() {
      return (builder: QueryBuilder<Notification>) => {
        builder
          .where('is_deleted', false)
          .where('is_read', false)
          .orderBy('priority', 'asc') // critical first
          .orderBy('created_at', 'asc');
      };
    },
    broadcast() {
      return (builder: QueryBuilder<Notification>) => {
        builder.where('is_broadcast', true).orderBy('created_at', 'desc');
      };
    },
    expired() {
      return (builder: QueryBuilder<Notification>) => {
        builder
          .where('expires_at', '<', new Date())
          .where('is_deleted', false);
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

// Forward declare related models to avoid circular dependency issues
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import type { User } from './user';
import type { NotificationTemplate } from './notification-template';
import type { NotificationDeliveryLog } from './notification-delivery-log';

export default Notification;
