import HeroDraftPage from '~/pages/herodraft/HeroDraftPage';
import { generateMeta } from '~/lib/seo';

export function meta() {
  return generateMeta({
    title: 'Hero Draft',
    description: "Captain's Mode hero drafting tool for Dota 2",
  });
}
export default HeroDraftPage;
