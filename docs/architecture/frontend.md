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
│   └── cypress/              # E2E tests
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
