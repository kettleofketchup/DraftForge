import { generateMeta } from '~/lib/seo';
import { Blog } from '../pages/blog/blog';

export function meta() {
  return generateMeta({
    title: 'Blog',
    description: 'News and updates from DraftForge',
    url: '/blog',
  });
}

export default function Home() {
  return <Blog />;
}
