import { About } from '../pages/about/about';
import type { Route } from './+types/home';

export function meta({}: Route.MetaArgs) {
  return [{ title: 'About Us' }, { name: 'description', content: 'About us!' }];
}

export default function Home() {
  return <About />;
}
