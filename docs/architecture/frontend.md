# Frontend Architecture

## Technology Stack

- **Framework**: React 18+
- **Language**: TypeScript
- **Build Tool**: Vite
- **Routing**: React Router
- **Styling**: TailwindCSS + Shadcn UI
- **State Management**: Zustand
- **Validation**: Zod
- **Notifications**: Sonner

## Project Structure

```
frontend/
├── app/
│   ├── components/
│   │   ├── <feature>/        # Feature components
│   │   │   ├── hooks/        # Colocated hooks
│   │   │   ├── edit/         # Edit forms
│   │   │   └── create/       # Create forms
│   │   ├── api/              # API helpers and types
│   │   ├── reusable/         # Shared components
│   │   └── ui/               # Shadcn UI primitives
│   ├── pages/
│   │   └── <page>/           # Route-level pages
│   │       ├── tabs/         # Tabbed subcomponents
│   │       └── components/   # Page-specific components
│   ├── routes/               # Route definitions
│   └── lib/                  # Utilities
├── tests/
│   ├── cypress/              # E2E tests (legacy)
│   └── playwright/           # E2E tests (primary)
└── public/                   # Static assets
```

## Routing Pattern

```tsx
// routes/users.tsx - Route definition
import UsersPage from '~/pages/users'
export default function UsersRoute() {
  return <UsersPage />
}

// pages/users/index.tsx - Page component
import UserCard from '~/components/user/UserCard'
export default function UsersPage() {
  return <main><UserCard /></main>
}
```

## State Management

Zustand stores for feature-specific state:

```typescript
import { create } from 'zustand'

const useUserStore = create((set) => ({
  user: null,
  setUser: (user) => set({ user }),
}))
```

## API Integration

### Zod Validation

All API responses validated with Zod schemas:

```typescript
import { z } from 'zod'

const UserSchema = z.object({
  id: z.number(),
  username: z.string(),
})

type User = z.infer<typeof UserSchema>
```

### Mutations with Toast

```typescript
import { toast } from 'sonner'

toast.promise(apiCall(data), {
  loading: 'Saving...',
  success: 'Saved!',
  error: (err) => `Failed: ${err.message}`,
})
```

## Component Guidelines

- Use Shadcn UI components from `~/components/ui/`
- Keep components small and focused
- Extract hooks to `hooks/` subdirectory
- Name hooks as `<what><action>Hook.tsx`

## Logging

```typescript
import { getLogger } from '~/lib/logger'
const log = getLogger('ComponentName')

log.debug('Details', { data })
log.error('Failed', error)
```

## Draft System Components

### Notification Components

The draft system includes notification components to alert captains when it's their turn:

| Component | Location | Description |
|-----------|----------|-------------|
| `FloatingDraftIndicator` | `components/draft/` | Fixed bottom-right notification with link to tournament |
| `DraftNotificationBadge` | `components/draft/` | Pulsing red dot on user avatar |
| `TurnIndicator` | `components/draft/roundView/` | Shows whose turn in draft modal |

### Active Draft Data

Active draft information is provided via the user's session data. When the user is logged in, the `current_user` API response includes an `active_drafts` array containing any drafts where the user has a pending turn.

```typescript
import { useUserStore } from '~/stores/userStore'

const { user } = useUserStore()

// Check if user has any active draft turns
const hasActiveTurn = user?.active_drafts?.length > 0

if (hasActiveTurn) {
  // Show notification, active_drafts contains tournament info
  const firstDraft = user.active_drafts[0]
  console.log(firstDraft.tournament_pk, firstDraft.tournament_name)
}
```

This data is automatically refreshed when the user store fetches the current user.

### Auto-Open Draft Modal

Navigate to tournament with `?draft=open` to auto-open the draft modal:

```
/tournament/123?draft=open
```

The `FloatingDraftIndicator` uses this pattern when clicked.
