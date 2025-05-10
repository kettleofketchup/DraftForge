
import type { UserType, UsersType } from '../user/types';
import axios from "./axios"
import type { GuildMember, GuildMembers } from '../user/types';
import type { GameType, TeamType, TournamentType } from '../tournament/types';

export async function fetchCurrentUser(): Promise<UserType> {
    const response = await axios.get<UserType>(`/current_user`);
    return response.data;
  }

  export async function fetchUsers(): Promise<UsersType> {
    const response = await axios.get<UsersType>(`/users`);
    return response.data;
  }

  export async function updateUser(): Promise<UsersType> {
    const response = await axios.get<UsersType>(`/users`);
    return response.data;
  }
  export async function get_dtx_members(): Promise<GuildMembers> {
    const response = await axios.get<GuildMembers>(`/dtx_members`);
    if ('members' in response.data) {
      console.log(response.data.members)
      return response.data.members;
    } else {
      throw new Error("Key 'members' not found in response data");
    }}

  export async function getTournaments(): Promise<UsersType> {
      const response = await axios.get<TournamentType>(`/tournaments`);
      return response.data;
  }

  export async function getTeams(): Promise<UsersType> {
    const response = await axios.get<TeamType>(`/teams`);
    return response.data;
  }

  export async function getGames(): Promise<UsersType> {
    const response = await axios.get<GameType>(`/games`);
    return response.data;
  }
