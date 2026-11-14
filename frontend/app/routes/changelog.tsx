import { generateMeta } from '~/lib/seo';
import { ChangelogPage } from '../pages/changelog/changelog';

export function meta() {
  return generateMeta({
    title: 'Changelog',
    description: 'Release notes for every DraftForge version',
    url: '/changelog',
  });
}

export default function Changelog() {
  return <ChangelogPage />;
}
