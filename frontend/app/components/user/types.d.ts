

export declare interface User {
    username: string;
    avatarUrl: string;
    is_staff: boolean;
    is_superuser: boolean;
    mmr?: integer;
    position?: string;
    steamid?: integer;


  }


export declare type Users = User[];

export interface UserProps {
}
