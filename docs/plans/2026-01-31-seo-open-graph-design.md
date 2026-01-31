# SEO and Open Graph Implementation Design

**Date:** 2026-01-31
**Status:** Implemented (Phase A + B)

## Overview

Add Open Graph and Twitter Card meta tags to DraftForge for rich social sharing previews.

## Goals

- **Phase A:** Static Open Graph tags with consistent branding across all routes
- **Phase B:** Dynamic meta tags pulling tournament/league names from data

## Architecture

```
frontend/app/
├── lib/
│   └── seo.ts              # SEO utilities and defaults
├── root.tsx                # Base HTML structure
└── routes/
    ├── home.tsx            # Route-specific meta
    ├── tournament.tsx      # Dynamic tournament meta (Phase B)
    └── ...
```

## Site Constants

- **Site Name:** DraftForge
- **Site URL:** https://dota.kettle.sh
- **Default Image:** /og-image.png (1280x800)
- **Default Description:** Dota 2 tournament management, team drafts, and captain's mode hero drafting

## SEO Utility (`lib/seo.ts`)

```typescript
const SITE_NAME = 'DraftForge';
const SITE_URL = 'https://dota.kettle.sh';
const DEFAULT_IMAGE = '/og-image.png';
const DEFAULT_DESCRIPTION = 'Dota 2 tournament management, team drafts, and captain\'s mode hero drafting';

export function generateMeta({
  title,
  description,
  image,
  url,
  type = 'website',
}: {
  title: string;
  description?: string;
  image?: string;
  url?: string;
  type?: 'website' | 'article';
}) {
  const fullTitle = `${title} | ${SITE_NAME}`;
  const desc = description || DEFAULT_DESCRIPTION;
  const img = image || DEFAULT_IMAGE;

  return [
    { title: fullTitle },
    { name: 'description', content: desc },
    { property: 'og:title', content: fullTitle },
    { property: 'og:description', content: desc },
    { property: 'og:image', content: img },
    { property: 'og:type', content: type },
    { property: 'og:site_name', content: SITE_NAME },
    { name: 'twitter:card', content: 'summary_large_image' },
    { name: 'twitter:title', content: fullTitle },
    { name: 'twitter:description', content: desc },
    { name: 'twitter:image', content: img },
  ];
}
```

## Route Meta Tags

| Route | Title | Description |
|-------|-------|-------------|
| `home.tsx` | Home | Manage Dota 2 tournaments, team drafts, and hero drafting |
| `tournaments.tsx` | Tournaments | Browse and manage Dota 2 tournaments |
| `tournament.tsx` | Tournament | Tournament brackets and team matchups |
| `leagues.tsx` | Leagues | Competitive Dota 2 league seasons |
| `league.tsx` | League | League standings and tournament schedule |
| `organizations.tsx` | Organizations | Dota 2 tournament organizers |
| `organization.tsx` | Organization | Organization profile and events |
| `leaderboard.tsx` | Leaderboard | Player rankings and league standings |
| `herodraft.tsx` | Hero Draft | Captain's Mode hero drafting tool |
| `about.tsx` | About | About DraftForge |
| `blog.tsx` | Blog | News and updates |
| `users.tsx` | Players | Player directory |
| `user.tsx` | Player Profile | Player stats and history |

## Implementation Phases

### Phase A: Static Open Graph

1. Create `frontend/app/lib/seo.ts` with `generateMeta()` helper
2. Copy `home.png` to `frontend/public/og-image.png`
3. Update all routes with static meta tags using `generateMeta()`

### Phase B: Dynamic Meta (Implemented)

1. Added loaders to detail routes:
   - `tournament.tsx` - Fetches tournament, shows name and team count
   - `league.tsx` - Fetches league, shows name and organization
   - `organization.tsx` - Fetches org, shows name and description excerpt
   - `user.tsx` - Fetches user, shows display name and MMR
2. Each loader has error handling with graceful fallback to static meta
3. Data passed to `meta()` function via React Router's loader/meta integration

## Testing

- Use [Facebook Sharing Debugger](https://developers.facebook.com/tools/debug/)
- Use [Twitter Card Validator](https://cards-dev.twitter.com/validator)
- Check meta tags in browser DevTools
