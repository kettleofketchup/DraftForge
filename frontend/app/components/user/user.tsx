import {
  createUser,
  deleteUser,
  fetchUser,
  updateUser,
} from '~/components/api/api';
import type { GuildMember, UserClassType, UserType } from '~/index';

import { getLogger } from '~/lib/logger';
import type { PositionsType } from './types';
const log = getLogger('user');

export class User implements UserClassType {
  username!: string;
  avatarUrl!: string;
  is_staff!: boolean;
  is_superuser!: boolean;
  nickname?: string | null;
  mmr?: number;
  position?: string;
  steamid?: number;
  avatar?: string;
  positions?: PositionsType;
  pk: number;
  discordNickname?: string | null;
  discordId?: string;
  guildNickname?: string | null;

  constructor(data: UserType) {
    Object.assign(this, data);
    this.pk = data.pk || 0;
  }

  async dbFetch(): Promise<UserType> {
    if (!this.pk) {
      log.error('Error fetching user data:');
      throw new Error('User primary key (pk) is not set.');
    }
    try {
      const data = await fetchUser(this.pk);
      Object.assign(this, data);
      return this as UserType;
    } catch (error) {
      log.error('Error fetching user data:', error);
      throw error;
    }
  }

  async dbUpdate(data: Partial<UserType>): Promise<UserType> {
    if (!this.pk) {
      this.dbFetch();
      if (!this.pk) throw new Error('User primary key (pk) is not set.');
    }

    try {
      const updatedData = await updateUser(this.pk, data);
      Object.assign(this, updatedData);
      return updatedData;
    } catch (error) {
      log.error('Error fetching user data:', error);
      throw error;
    }
  }

  async dbDelete(): Promise<void> {
    if (!this.pk) {
      this.dbFetch();
      if (!this.pk) throw new Error('User primary key (pk) is not set.');
    }
    try {
      await deleteUser(this.pk);
      Object.assign({});
    } catch (error) {
      log.error('Error fetching user data:', error);
      throw error;
    }
  }
  async dbCreate(): Promise<UserType> {
    try {
      const data = await createUser(this as UserType);
      Object.assign(this, data);
      return data;
    } catch (error) {
      log.error('Error creating user data:', error);
      throw error;
    }
  }
  // Mutates the current instance with values from a GuildMember
  setFromGuildMember(member: GuildMember): void {
    if (!member) {
      log.debug('Guild member is not defined.');
    }
    if (!member.user) {
      throw new Error('Guild member is missing user info.');
    }

    this.nickname = member.nick ?? member.user.global_name ?? null;

    this.discordId = member.user.id;
    this.username = member.user.username;
    this.avatar = member.user.avatar ?? undefined;
    this.discordNickname = member.user.global_name ?? null;
    this.guildNickname = member.nick ?? null;
    log.debug('User set from GuildMember:', this, member);
  }
  getAvatarUrl(): string {
    if (!this.avatar) {
      throw new Error('Avatar is not set.');
    }
    return `https://cdn.discordapp.com/avatars/${this.discordId}/${this.avatar}.png`;
  }
}
