import HomePage from '~/pages/home/home';

export function meta() {
  return [{ title: 'DTX' }, { name: 'description', content: 'Login' }];
}

export default function Home() {
  return <HomePage />;
}
