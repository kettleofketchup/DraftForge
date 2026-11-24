import api from '~/components/api/axios';
import {
  SteamVerificationOutSchema,
  type SteamVerificationIn,
  type SteamVerificationOut,
} from './schemas';

const path = (userPk: number): string => `/users/${userPk}/steam-verification/`;

export async function getSteamVerification(
  userPk: number,
): Promise<SteamVerificationOut> {
  const response = await api.get(path(userPk));
  return SteamVerificationOutSchema.parse(response.data);
}

export async function setSteamVerification(
  userPk: number,
  verified: boolean,
  steamAccountId: number,
): Promise<SteamVerificationOut> {
  const body: SteamVerificationIn = {
    verified,
    steam_account_id: steamAccountId,
  };
  const response = await api.post(path(userPk), body);
  return SteamVerificationOutSchema.parse(response.data);
}
