import HeroDraftPage from '~/pages/herodraft/HeroDraftPage';
import { generateMeta } from '~/lib/seo';
import type { HeroDraftSSR } from '~/lib/ssr-types';
import type { Route } from './+types/herodraft';

export async function loader({ params }: Route.LoaderArgs) {
  const { fetchSSR } = await import('~/lib/ssr.server');
  const draft = await fetchSSR<HeroDraftSSR>(`/herodraft/${params.id}/ssr/`);
  return { draft };
}

export async function clientLoader() {
  // HeroDraft loads its data via WebSocket, not REST.
  // Return null to prevent unnecessary server round-trips on client navigation.
  return { draft: null };
}

export function meta({ data }: Route.MetaArgs) {
  const draft = data?.draft;

  if (draft?.tournament_name) {
    const teams = draft.team_names?.join(' vs ') || '';
    const teamsText = teams ? ` — ${teams}` : '';
    return generateMeta({
      title: `Hero Draft: ${draft.tournament_name}`,
      description: `Captain's Mode hero draft${teamsText} — ${draft.tournament_name} on DraftForge`,
    });
  }

  return generateMeta({
    title: 'Hero Draft',
    description: "Captain's Mode hero drafting tool for Dota 2",
  });
}

export default HeroDraftPage;
