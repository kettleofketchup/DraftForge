# TypeScript Frontend Agent

Expert agent for React/TypeScript frontend development in the DTX website project.

## Project Context

**Goal**: Website that helps manage DTX, a Dota2 gaming organization.

**Stack**:
- React + TypeScript + Vite
- React Router for routing
- TailwindCSS for styling
- Shadcn UI for components
- Zustand for state management
- Sonner for toast notifications
- Zod for API validation

**Location**: `./frontend/`

## Directory Structure

```
frontend/
  app/
    components/
      <feature>/           # Feature components (user, tournament, draft)
        hooks/             # Colocated hooks
        edit/              # Edit forms (Form.tsx, Modal.tsx)
        create/            # Create forms (Form.tsx, Modal.tsx)
      api/                 # API helpers and types
      reusable/            # Shared generic components
      ui/                  # Shadcn UI primitives
    pages/
      <page>/              # Route-level composition
        tabs/              # Tabbed subcomponents
        components/        # Page-specific components
    routes/                # Route definitions
    lib/                   # Utilities (logger)
```

## Routing Pattern

```tsx
// frontend/app/routes/users.tsx
import UsersPage from '~/pages/users'
export default function UsersRoute() {
  return <UsersPage />
}

// frontend/app/pages/users/index.tsx
import UserCard from '~/components/user/UserCard'
export default function UsersPage() {
  return <main><UserCard /></main>
}
```

## Hook Naming Convention

Name hooks as `<what><action>Hook.tsx`:
- `rebuildTeamsHook.tsx`
- `useUserProfileHook.tsx`
- `fetchPostsHook.tsx`

## API Patterns

### Zod Validation (Standard)
Use Zod schemas for all API request/response validation:

```ts
import { z } from 'zod'

const UserSchema = z.object({
  id: z.number(),
  username: z.string(),
  email: z.string().email(),
})

type User = z.infer<typeof UserSchema>

// Validate response
const response = await api.get('/users/')
const user = UserSchema.parse(response.data)
```

**Note**: Legacy code may not use Zod. When modifying existing API calls, migrate them to Zod validation.

### POST/PUT/DELETE (Mutations)
Use `toast.promise` from sonner:

```ts
import { toast } from 'sonner'
import { getLogger } from '~/lib/logger'

const log = getLogger('MyComponent')

toast.promise(apiCall(data), {
  loading: 'Processing...',
  success: (resp) => {
    setData(resp)
    return 'Success!'
  },
  error: (err) => {
    log.error('Failed', err)
    return `Failed: ${err?.response?.data ?? String(err)}`
  },
})
```

### GET (Reads)
Fetch quietly with UI loading states (spinners, skeletons). No toasts for reads.

## Logging

```ts
import { getLogger } from '~/lib/logger'
const log = getLogger('ModuleName')

log.debug('Detailed info', { data })
log.info('General info')
log.warn('Warning')
log.error('Error', err)
```

Never log sensitive information (passwords, tokens).

## State Management

Use Zustand for local/feature state:
- `useUserStore` - User-related state
- Create focused stores per feature, not one global store

## Component Guidelines

- Use Shadcn UI components from `~/components/ui/`
- Keep components small and focused
- Extract repeated UI into `reusable/` components
- Use React.FC for components with children
- Follow React hooks rules (no conditional hooks)
- Place complex logic in hooks or utils

## TypeScript Standards

- Type everything: API payloads, component props
- Use Zod schemas for runtime validation
- Use interfaces for data structures
- Prefer immutable data (`const`, `readonly`)
- Use optional chaining (`?.`) and nullish coalescing (`??`)
- Follow PascalCase for components/interfaces, camelCase for variables/functions

## Steam API

Frontend only receives Steam data from the Django backend. Never call Steam API directly from TypeScript.
