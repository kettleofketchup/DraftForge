import api from '~/components/api/axios';
import { TournamentViewerSchema, type TournamentViewer } from './schemas';

export async function getTournamentViewer(
  tournamentPk: number,
): Promise<TournamentViewer> {
  const response = await api.get(`/tournaments/${tournamentPk}/viewer/`);
  return TournamentViewerSchema.parse(response.data);
}
