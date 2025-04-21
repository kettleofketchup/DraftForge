
import type { User, Users } from '../user/types';
import axios from "./axios"



export async function fetchCurrentUser(): Promise<User> {
    const response = await axios.get<User>(`/current_user`);
    return response.data;
  }

  export async function fetchUsers(): Promise<Users> {
    const response = await axios.get<Users>(`/users`);
    return response.data;
  }
