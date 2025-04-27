

export declare interface User {
    username: string;
    nickname?: string;
    avatarUrl: string;
    is_staff: boolean;
    is_superuser: boolean;
    mmr?: integer;
    position?: string;
    steamid?: integer;
    avatar?: string;
    discordId?: string;
    pk?: integer;

  }


export declare type Users = User[];

export interface UserProps {
}
