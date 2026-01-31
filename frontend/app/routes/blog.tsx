import { Blog } from '../pages/blog/blog';
import { generateMeta } from '~/lib/seo';

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
