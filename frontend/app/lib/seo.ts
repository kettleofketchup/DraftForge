// SEO utilities for Open Graph and Twitter Card meta tags

const SITE_NAME = 'DraftForge';
const SITE_URL = 'https://dota.kettle.sh';
const DEFAULT_IMAGE = '/og-image.png';
const DEFAULT_DESCRIPTION =
  "Dota 2 tournament management, team drafts, and captain's mode hero drafting";

interface MetaOptions {
  title: string;
  description?: string;
  image?: string;
  url?: string;
  type?: 'website' | 'article';
}

/**
 * Generate complete meta tags array for a route.
 * Includes standard meta, Open Graph, and Twitter Card tags.
 */
export function generateMeta({
  title,
  description,
  image,
  url,
  type = 'website',
}: MetaOptions) {
  const fullTitle = `${title} | ${SITE_NAME}`;
  const desc = description || DEFAULT_DESCRIPTION;
  const img = image?.startsWith('http') ? image : `${SITE_URL}${image || DEFAULT_IMAGE}`;
  const pageUrl = url ? `${SITE_URL}${url}` : undefined;

  const meta = [
    // Standard meta
    { title: fullTitle },
    { name: 'description', content: desc },

    // Open Graph
    { property: 'og:title', content: fullTitle },
    { property: 'og:description', content: desc },
    { property: 'og:image', content: img },
    { property: 'og:image:width', content: '1280' },
    { property: 'og:image:height', content: '800' },
    { property: 'og:type', content: type },
    { property: 'og:site_name', content: SITE_NAME },

    // Twitter Card
    { name: 'twitter:card', content: 'summary_large_image' },
    { name: 'twitter:title', content: fullTitle },
    { name: 'twitter:description', content: desc },
    { name: 'twitter:image', content: img },
  ];

  // Add URL if provided
  if (pageUrl) {
    meta.push({ property: 'og:url', content: pageUrl });
    meta.push({ name: 'twitter:url', content: pageUrl });
  }

  return meta;
}

export { SITE_NAME, SITE_URL, DEFAULT_IMAGE, DEFAULT_DESCRIPTION };
