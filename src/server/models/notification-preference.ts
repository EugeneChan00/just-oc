/**
 * User Notification Preference Model
 * 
 * Represents a user's notification preference for a specific channel.
 */

import { Model, QueryBuilder } from 'objection';
import { z } from 'zod';

// Enum schemas
export const DeliveryMode = ['real_time', 'hourly', 'daily'] as const;
export type DeliveryModeValue = typeof DeliveryMode[number];

// Zod schema for preference creation
export const UserNotificationPreferenceCreateSchema = z.object({
  userId: z.string().uuid(),
  channelId: z.string().uuid(),
  isEnabled: z.boolean().default(true),
  deliveryMode: z.enum(DeliveryMode).default('real_time'),
  digestTimezone: z.string().max(50).default('UTC'),
  digestTime: z.string().regex(/^\d{2}:\d{2}(:\d{2})?$/).nullable().optional(),
  quietHoursEnabled: z.boolean().default(false),
  quietHoursStart: z.string().regex(/^\d{2}:\d{2}(:\d{2})?$/).nullable().optional(),
  quietHoursEnd: z.string().regex(/^\d{2}:\d{2}(:\d{2})?$/).nullable().optional(),
  quietHoursTimezone: z.string().max(50).default('UTC'),
  disabledNotificationTypes: z.array(z.string()).default([]),
  description: z.string().max(500).nullable().optional(),
});

export const UserNotificationPreferenceUpdateSchema = 
  UserNotificationPreferenceCreateSchema.partial();

export type UserNotificationPreferenceCreateInput = 
  z.infer<typeof UserNotificationPreferenceCreateSchema>;
export type UserNotificationPreferenceUpdateInput = 
  z.infer<typeof UserNotificationPreferenceUpdateSchema>;

// Database model class
export class UserNotificationPreference extends Model {
  static tableName = 'user_notification_preferences';

  // Columns
  id!: string;
  userId!: string;
  channelId!: string;
  isEnabled!: boolean;
  deliveryMode!: DeliveryModeValue;
  digestTimezone!: string;
  digestTime!: string | null;
  quietHoursEnabled!: boolean;
  quietHoursStart!: string | null;
  quietHoursEnd!: string | null;
  quietHoursTimezone!: string;
  disabledNotificationTypes!: string[];
  description!: string | null;
  createdAt!: Date;
  updatedAt!: Date;

  // Relationships
  static relationMappings = {
    user: {
      relation: Model.BelongsToOneRelation,
      modelClass: () => User,
      join: {
        from: 'user_notification_preferences.user_id',
        to: 'users.id',
      },
    },
    channel: {
      relation: Model.BelongsToOneRelation,
      modelClass: () => DeliveryChannel,
      join: {
        from: 'user_notification_preferences.channel_id',
        to: 'delivery_channels.id',
      },
    },
  };

  // Query scopes
  static queryScopes = {
    forUser(userId: string) {
      return (builder: QueryBuilder<UserNotificationPreference>) => {
        builder.where('user_id', userId);
      };
    },
    enabled() {
      return (builder: QueryBuilder<UserNotificationPreference>) => {
        builder.where('is_enabled', true);
      };
    },
    forChannel(channelId: string) {
      return (builder: QueryBuilder<UserNotificationPreference>) => {
        builder.where('channel_id', channelId);
      };
    },
    digestMode() {
      return (builder: QueryBuilder<UserNotificationPreference>) => {
        builder.whereNot('delivery_mode', 'real_time');
      };
    },
  };

  // Check if a notification type is allowed
  isNotificationTypeAllowed(notificationType: string): boolean {
    return !this.disabledNotificationTypes.includes(notificationType);
  }

  // Check if currently in quiet hours (using given timezone)
  isInQuietHours(timezone: string = this.quietHoursTimezone): boolean {
    if (!this.quietHoursEnabled || !this.quietHoursStart || !this.quietHoursEnd) {
      return false;
    }

    // Get current time in the user's timezone
    const now = new Date();
    const formatter = new Intl.DateTimeFormat('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZone: timezone,
    });
    const currentTime = formatter.format(now);
    
    // Compare times (simple lexicographic comparison works for HH:mm:ss format)
    return currentTime >= this.quietHoursStart && currentTime <= this.quietHoursEnd;
  }

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
import type { User } from './user';
import type { DeliveryChannel } from './delivery-channel';

export default UserNotificationPreference;
