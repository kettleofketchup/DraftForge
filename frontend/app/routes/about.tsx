import { About } from '../pages/about/about';
import { generateMeta } from '~/lib/seo';

export function meta() {
  return generateMeta({
    title: 'About',
    description: 'Learn about DraftForge and the team behind it',
    url: '/about',
  });
}

export default function Home() {
  return <About />;
}
