
import type { User } from '../user/types';
import axios from "./axios"



export async function fetchCurrentUser(): Promise<User> {
    const response = await axios.get<User>(`/current_user`);


    return response.data;
  }
