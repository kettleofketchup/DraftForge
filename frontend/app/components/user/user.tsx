

import type { UserType, GuildMember, GuildMembers, UserClassType } from "./types";



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
  pk?: number;
  discordNickname?: string | null;
  discordId?: string;
  guildNickname?: string | null;

  constructor ( data: UserType  ){
      Object.assign(this, data);
    }



  // Mutates the current instance with values from a GuildMember
  setFromGuildMember(member: GuildMember): void {
    if (!member.user) {
      throw new Error("Guild member is missing user info.");
    }

    if (! this.nickname){
      this.nickname = member.nick ?? member.user.global_name ?? null;
    }
    this.discordId = member.user.id;
    this.username = member.user.username;
    this.avatar = member.user.avatar ?? undefined;
    this.discordNickname = member.user.global_name ?? null;
    this.guildNickname = member.znick ?? null;
    this.avatarUrl = this.getAvatarUrl()

  }
  getAvatarUrl(): string {
    if (!this.avatar) {
      throw new Error("Avatar is not set.");
    }
    return `https://cdn.discordapp.com/avatars/${this.discordId}/${this.avatar}.png`;
  }


}
