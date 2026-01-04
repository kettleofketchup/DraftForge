# Zod Form Skills Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create Claude Code skills for Zod schema validation and React Hook Form integration, plus update the TypeScript frontend agent to reference them.

**Architecture:** Three new skills (zod-schema, zod-form-resolver, zod-api-hook) provide pattern documentation for form validation. The existing typescript-frontend agent gets updated to reference these skills for form work.

**Tech Stack:** Zod, React Hook Form, @hookform/resolvers, Shadcn UI Form components

---

## Task 1: Create Zod Schema Skill

**Files:**
- Create: `.claude/skills/zod-schema.md`

**Step 1: Create the zod-schema skill file**

```markdown
# Zod Schema Skill

Use this skill when creating or modifying Zod schemas for API validation and TypeScript type inference.

## When to Use

- Creating new API response/request schemas
- Defining form validation schemas
- Generating TypeScript types from schemas
- Validating external data (API responses, form inputs)

## Schema Location Convention

Place schemas in `schemas.ts` files colocated with their feature:

```
frontend/app/components/
  user/schemas.ts        # UserSchema, PositionSchema
  game/schemas.ts        # GameSchema
  tournament/schemas.ts  # TournamentSchema
  team/schemas.ts        # TeamSchema
  draft/schemas.ts       # DraftSchema
```

## Core Patterns

### Basic Schema Definition

```typescript
import { z } from 'zod';

// Define the schema
export const UserSchema = z.object({
  pk: z.number().min(0).optional(),
  username: z.string().min(2).max(100),
  email: z.string().email(),
  avatarUrl: z.string().url().optional(),
  isActive: z.boolean().default(true),
});

// Infer TypeScript type from schema
export type UserType = z.infer<typeof UserSchema>;
```

### Nested Schemas

```typescript
export const PositionSchema = z.object({
  carry: z.number().min(0).max(5),
  mid: z.number().min(0).max(5),
  offlane: z.number().min(0).max(5),
  soft_support: z.number().min(0).max(5),
  hard_support: z.number().min(0).max(5),
});

export const UserSchema = z.object({
  username: z.string(),
  positions: PositionSchema.optional(),
});
```

### Nullable vs Optional

```typescript
z.string().optional()           // string | undefined
z.string().nullable()           // string | null
z.string().nullable().optional() // string | null | undefined
```

### Custom Error Messages

```typescript
z.string().min(2, { message: 'Username must be at least 2 characters.' })
z.number().min(0, { message: 'Value cannot be negative.' })
z.string().email({ message: 'Invalid email address.' })
```

### Enums

```typescript
export const TournamentStateSchema = z.enum(['draft', 'active', 'completed']);
export type TournamentState = z.infer<typeof TournamentStateSchema>;
```

### Arrays

```typescript
export const TeamSchema = z.object({
  name: z.string(),
  members: z.array(UserSchema),
});
```

### Schema Composition

```typescript
// Extend a schema
const AdminUserSchema = UserSchema.extend({
  permissions: z.array(z.string()),
});

// Pick fields
const UserSummarySchema = UserSchema.pick({ pk: true, username: true });

// Omit fields
const CreateUserSchema = UserSchema.omit({ pk: true });

// Partial (all fields optional)
const UpdateUserSchema = UserSchema.partial();
```

## API Response Validation

```typescript
import { z } from 'zod';
import { UserSchema } from '~/components/user/schemas';

const response = await api.get('/users/me/');
const user = UserSchema.parse(response.data); // Throws on invalid data

// Or safe parsing (no throw)
const result = UserSchema.safeParse(response.data);
if (result.success) {
  const user = result.data;
} else {
  console.error(result.error);
}
```

## Common Validators

```typescript
// Strings
z.string().min(1)               // Required (non-empty)
z.string().max(100)             // Max length
z.string().email()              // Email format
z.string().url()                // URL format
z.string().uuid()               // UUID format
z.string().regex(/pattern/)     // Regex match

// Numbers
z.number().int()                // Integer only
z.number().positive()           // > 0
z.number().nonnegative()        // >= 0
z.number().min(0).max(100)      // Range

// Dates
z.string().datetime()           // ISO datetime string
z.coerce.date()                 // Coerce to Date object

// Transforms
z.string().transform(s => s.toLowerCase())
z.string().trim()
```

## Reference

- [Zod Documentation](https://zod.dev/)
- [Zod GitHub](https://github.com/colinhacks/zod)
```

**Step 2: Verify the file was created**

Run: `cat .claude/skills/zod-schema.md | head -20`
Expected: Shows the skill header and "When to Use" section

**Step 3: Commit**

```bash
git add .claude/skills/zod-schema.md
git commit -m "feat: add zod-schema skill for API validation patterns"
```

---

## Task 2: Create Zod Form Resolver Skill

**Files:**
- Create: `.claude/skills/zod-form-resolver.md`

**Step 1: Create the zod-form-resolver skill file**

```markdown
# Zod Form Resolver Skill

Use this skill when building forms with React Hook Form and Zod validation using Shadcn UI components.

## When to Use

- Creating new forms with validation
- Migrating legacy useState forms to React Hook Form
- Adding validation to existing forms
- Building edit/create modals with forms

## Prerequisites

Required packages (already installed in this project):
- `react-hook-form`
- `@hookform/resolvers`
- `zod`

## Form Setup Pattern

### 1. Define Schema (in schemas.ts)

```typescript
// ~/components/user/schemas.ts
import { z } from 'zod';

export const UserFormSchema = z.object({
  username: z.string().min(2, 'Username required'),
  email: z.string().email('Invalid email'),
  mmr: z.number().min(0).nullable().optional(),
});

export type UserFormData = z.infer<typeof UserFormSchema>;
```

### 2. Initialize Form with Resolver

```typescript
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { UserFormSchema } from '~/components/user/schemas';

const form = useForm<z.infer<typeof UserFormSchema>>({
  resolver: zodResolver(UserFormSchema),
  defaultValues: {
    username: '',
    email: '',
    mmr: null,
  },
});
```

### 3. Build Form with Shadcn Components

```typescript
import { Form, FormField, FormItem, FormLabel, FormControl, FormMessage } from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Button } from '~/components/ui/button';

return (
  <Form {...form}>
    <form onSubmit={form.handleSubmit(onSubmit)}>
      <FormField
        control={form.control}
        name="username"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Username</FormLabel>
            <FormControl>
              <Input placeholder="Enter username" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="email"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Email</FormLabel>
            <FormControl>
              <Input type="email" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <Button type="submit">Submit</Button>
    </form>
  </Form>
);
```

### 4. Handle Submit with Toast

```typescript
import { toast } from 'sonner';
import { getLogger } from '~/lib/logger';

const log = getLogger('UserForm');

function onSubmit(data: z.infer<typeof UserFormSchema>) {
  toast.promise(UpdateUser(data), {
    loading: 'Saving...',
    success: (response) => {
      setUser(response);
      return 'User updated!';
    },
    error: (err) => {
      log.error('Failed to update user', err);
      return `Failed: ${err?.response?.data ?? String(err)}`;
    },
  });
}
```

## Complete Form Component Example

```typescript
// ~/components/user/userCard/editForm.tsx
import React from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';

import { UpdateUser } from '~/components/api/api';
import { Button } from '~/components/ui/button';
import { DialogClose } from '~/components/ui/dialog';
import { Form, FormField, FormItem, FormLabel, FormControl, FormMessage } from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { UserFormSchema } from '~/components/user/schemas';
import { getLogger } from '~/lib/logger';

const log = getLogger('UserEditForm');

interface UserEditFormProps {
  user: z.infer<typeof UserFormSchema>;
  onSuccess?: (data: z.infer<typeof UserFormSchema>) => void;
}

export const UserEditForm: React.FC<UserEditFormProps> = ({ user, onSuccess }) => {
  const form = useForm<z.infer<typeof UserFormSchema>>({
    resolver: zodResolver(UserFormSchema),
    defaultValues: user,
  });

  function onSubmit(data: z.infer<typeof UserFormSchema>) {
    toast.promise(UpdateUser(data), {
      loading: 'Saving...',
      success: (response) => {
        onSuccess?.(response);
        return 'User updated!';
      },
      error: (err) => {
        log.error('Update failed', err);
        return `Failed: ${err?.response?.data ?? String(err)}`;
      },
    });
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="username"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Username</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button type="submit">Save</Button>
        </div>
      </form>
    </Form>
  );
};
```

## Form Field Types

### Select Field

```typescript
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '~/components/ui/select';

<FormField
  control={form.control}
  name="role"
  render={({ field }) => (
    <FormItem>
      <FormLabel>Role</FormLabel>
      <Select onValueChange={field.onChange} defaultValue={field.value}>
        <FormControl>
          <SelectTrigger>
            <SelectValue placeholder="Select role" />
          </SelectTrigger>
        </FormControl>
        <SelectContent>
          <SelectItem value="admin">Admin</SelectItem>
          <SelectItem value="user">User</SelectItem>
        </SelectContent>
      </Select>
      <FormMessage />
    </FormItem>
  )}
/>
```

### Number Field

```typescript
<FormField
  control={form.control}
  name="mmr"
  render={({ field }) => (
    <FormItem>
      <FormLabel>MMR</FormLabel>
      <FormControl>
        <Input
          type="number"
          {...field}
          onChange={(e) => field.onChange(e.target.valueAsNumber || null)}
        />
      </FormControl>
      <FormMessage />
    </FormItem>
  )}
/>
```

### Checkbox Field

```typescript
import { Checkbox } from '~/components/ui/checkbox';

<FormField
  control={form.control}
  name="isActive"
  render={({ field }) => (
    <FormItem className="flex items-center gap-2">
      <FormControl>
        <Checkbox checked={field.value} onCheckedChange={field.onChange} />
      </FormControl>
      <FormLabel>Active</FormLabel>
    </FormItem>
  )}
/>
```

## Migration from useState Forms

### Before (Legacy Pattern)

```typescript
const [form, setForm] = useState<UserType>({} as UserType);
const handleChange = (field: keyof UserType, value: any) => {
  setForm((prev) => ({ ...prev, [field]: value }));
};

<input
  value={form.username ?? ''}
  onChange={(e) => handleChange('username', e.target.value)}
/>
```

### After (React Hook Form + Zod)

```typescript
const form = useForm<z.infer<typeof UserSchema>>({
  resolver: zodResolver(UserSchema),
  defaultValues: { username: '' },
});

<FormField
  control={form.control}
  name="username"
  render={({ field }) => (
    <FormItem>
      <FormControl>
        <Input {...field} />
      </FormControl>
      <FormMessage />
    </FormItem>
  )}
/>
```

## Reference

- [Shadcn Form Docs](https://ui.shadcn.com/docs/components/form)
- [React Hook Form Docs](https://react-hook-form.com/)
- [Zod Resolver Docs](https://github.com/react-hook-form/resolvers#zod)
```

**Step 2: Verify the file was created**

Run: `cat .claude/skills/zod-form-resolver.md | head -20`
Expected: Shows the skill header and "When to Use" section

**Step 3: Commit**

```bash
git add .claude/skills/zod-form-resolver.md
git commit -m "feat: add zod-form-resolver skill for React Hook Form patterns"
```

---

## Task 3: Create Zod API Hook Skill

**Files:**
- Create: `.claude/skills/zod-api-hook.md`

**Step 1: Create the zod-api-hook skill file**

```markdown
# Zod API Hook Skill

Use this skill when creating API hooks that fetch, validate, and mutate data with Zod schemas.

## When to Use

- Creating new API hooks for data fetching
- Adding validation to API responses
- Building mutation hooks (create/update/delete)
- Integrating API calls with toast notifications

## Hook Location Convention

Place hooks in `hooks/` directories colocated with their feature:

```
frontend/app/components/
  user/
    hooks/
      useUserFetchHook.tsx
      useUserUpdateHook.tsx
    schemas.ts
  game/
    hooks/
      createGameHook.tsx
      fetchGamesHook.tsx
    schemas.ts
```

## Hook Naming Convention

Name hooks as `<what><action>Hook.tsx`:
- `fetchUsersHook.tsx` - GET multiple
- `fetchUserHook.tsx` - GET single
- `createUserHook.tsx` - POST
- `updateUserHook.tsx` - PUT/PATCH
- `deleteUserHook.tsx` - DELETE

## Fetch Hook Pattern (GET)

```typescript
// ~/components/user/hooks/fetchUsersHook.tsx
import { useEffect, useState } from 'react';
import { z } from 'zod';
import { api } from '~/components/api/api';
import { UserSchema } from '~/components/user/schemas';
import { getLogger } from '~/lib/logger';

const log = getLogger('fetchUsersHook');

const UsersResponseSchema = z.array(UserSchema);

export function useFetchUsers() {
  const [users, setUsers] = useState<z.infer<typeof UsersResponseSchema>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    async function fetchUsers() {
      try {
        setLoading(true);
        const response = await api.get('/users/');
        const validated = UsersResponseSchema.parse(response.data);
        setUsers(validated);
      } catch (err) {
        log.error('Failed to fetch users', err);
        setError(err instanceof Error ? err : new Error(String(err)));
      } finally {
        setLoading(false);
      }
    }
    fetchUsers();
  }, []);

  return { users, loading, error, refetch: () => {} };
}
```

## Mutation Hook Pattern (POST/PUT/DELETE)

```typescript
// ~/components/user/hooks/updateUserHook.tsx
import { toast } from 'sonner';
import { z } from 'zod';
import { api } from '~/components/api/api';
import { UserSchema } from '~/components/user/schemas';
import { getLogger } from '~/lib/logger';

const log = getLogger('updateUserHook');

type UserInput = z.infer<typeof UserSchema>;
type UserResponse = z.infer<typeof UserSchema>;

export async function updateUser(data: UserInput): Promise<UserResponse> {
  const response = await api.put(`/users/${data.pk}/`, data);
  return UserSchema.parse(response.data);
}

// Usage with toast.promise
export function useUpdateUser() {
  const update = (data: UserInput, onSuccess?: (user: UserResponse) => void) => {
    toast.promise(updateUser(data), {
      loading: 'Saving...',
      success: (user) => {
        onSuccess?.(user);
        return 'User updated!';
      },
      error: (err) => {
        log.error('Update failed', err);
        return `Failed: ${err?.response?.data ?? String(err)}`;
      },
    });
  };

  return { update };
}
```

## Create Hook Pattern

```typescript
// ~/components/game/hooks/createGameHook.tsx
import { toast } from 'sonner';
import { z } from 'zod';
import { api } from '~/components/api/api';
import { GameSchema } from '~/components/game/schemas';
import { getLogger } from '~/lib/logger';

const log = getLogger('createGameHook');

// Define input schema (omit pk for creation)
const CreateGameInputSchema = GameSchema.omit({ pk: true });
type CreateGameInput = z.infer<typeof CreateGameInputSchema>;
type GameResponse = z.infer<typeof GameSchema>;

export async function createGame(data: CreateGameInput): Promise<GameResponse> {
  const response = await api.post('/games/', data);
  return GameSchema.parse(response.data);
}

export function useCreateGame() {
  const create = (data: CreateGameInput, onSuccess?: (game: GameResponse) => void) => {
    toast.promise(createGame(data), {
      loading: 'Creating game...',
      success: (game) => {
        onSuccess?.(game);
        return 'Game created!';
      },
      error: (err) => {
        log.error('Create failed', err);
        return `Failed: ${err?.response?.data ?? String(err)}`;
      },
    });
  };

  return { create };
}
```

## Delete Hook Pattern

```typescript
// ~/components/game/hooks/deleteGameHook.tsx
import { toast } from 'sonner';
import { api } from '~/components/api/api';
import { getLogger } from '~/lib/logger';

const log = getLogger('deleteGameHook');

export async function deleteGame(pk: number): Promise<void> {
  await api.delete(`/games/${pk}/`);
}

export function useDeleteGame() {
  const remove = (pk: number, onSuccess?: () => void) => {
    toast.promise(deleteGame(pk), {
      loading: 'Deleting...',
      success: () => {
        onSuccess?.();
        return 'Game deleted!';
      },
      error: (err) => {
        log.error('Delete failed', err);
        return `Failed: ${err?.response?.data ?? String(err)}`;
      },
    });
  };

  return { remove };
}
```

## Safe Parse Pattern (for non-critical validation)

```typescript
const result = UserSchema.safeParse(response.data);
if (result.success) {
  setUser(result.data);
} else {
  log.warn('Invalid user data', result.error.issues);
  // Handle gracefully - maybe use partial data or defaults
}
```

## Type-Safe API Client Pattern

```typescript
// ~/components/api/typedApi.ts
import { z } from 'zod';
import { api } from './api';

export async function typedGet<T>(
  url: string,
  schema: z.ZodType<T>
): Promise<T> {
  const response = await api.get(url);
  return schema.parse(response.data);
}

export async function typedPost<TInput, TOutput>(
  url: string,
  data: TInput,
  outputSchema: z.ZodType<TOutput>
): Promise<TOutput> {
  const response = await api.post(url, data);
  return outputSchema.parse(response.data);
}

// Usage
const user = await typedGet('/users/me/', UserSchema);
const newGame = await typedPost('/games/', gameData, GameSchema);
```

## Integration with Form Hooks

```typescript
// Form component using both skills together
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useCreateGame } from '~/components/game/hooks/createGameHook';
import { GameFormSchema } from '~/components/game/schemas';

export const GameCreateForm: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const { create } = useCreateGame();

  const form = useForm<z.infer<typeof GameFormSchema>>({
    resolver: zodResolver(GameFormSchema),
    defaultValues: { name: '', date_played: '' },
  });

  function onSubmit(data: z.infer<typeof GameFormSchema>) {
    create(data, () => {
      form.reset();
      onClose();
    });
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)}>
        {/* FormFields here */}
      </form>
    </Form>
  );
};
```

## Reference

- @zod-schema - Schema definition patterns
- @zod-form-resolver - Form integration patterns
```

**Step 2: Verify the file was created**

Run: `cat .claude/skills/zod-api-hook.md | head -20`
Expected: Shows the skill header and "When to Use" section

**Step 3: Commit**

```bash
git add .claude/skills/zod-api-hook.md
git commit -m "feat: add zod-api-hook skill for API validation patterns"
```

---

## Task 4: Update TypeScript Frontend Agent

**Files:**
- Modify: `.claude/agents/typescript-frontend.md`

**Step 1: Read current agent file**

Run: `cat .claude/agents/typescript-frontend.md`
Expected: Shows current agent content

**Step 2: Update agent to reference Zod skills**

Add a new "Skills Reference" section and update the "API Patterns" section to reference the skills. Insert after line 85 (after the existing API Patterns section):

```markdown
## Skills Reference

When working on forms and API validation, use these skills:

| Skill | When to Use |
|-------|-------------|
| @zod-schema | Creating/modifying Zod schemas for validation |
| @zod-form-resolver | Building forms with React Hook Form + Shadcn UI |
| @zod-api-hook | Creating API hooks with validation |

### Form Work Checklist

When creating or modifying forms:
1. Check @zod-schema for schema patterns
2. Check @zod-form-resolver for form component structure
3. Check @zod-api-hook for submission/mutation patterns

### Migration Priority

Legacy forms using `useState` should be migrated to React Hook Form + Zod:
- `components/game/create/createForm.tsx` - Uses useState, needs migration
- `components/tournament/create/editForm.tsx` - Uses useState, needs migration
- `components/user/userCard/editForm.tsx` - Uses useState, needs migration
```

**Step 3: Verify the changes**

Run: `grep -A5 "Skills Reference" .claude/agents/typescript-frontend.md`
Expected: Shows the new Skills Reference section

**Step 4: Commit**

```bash
git add .claude/agents/typescript-frontend.md
git commit -m "feat: update typescript-frontend agent with Zod skill references"
```

---

## Task 5: Update CLAUDE.md Skills List

**Files:**
- Modify: `.claude/CLAUDE.md`

**Step 1: Update the skills list**

Find the "Skills Available" section and add the new skills:

```markdown
## Skills Available

- `visual-debugging` - Chrome MCP browser automation for debugging
- `mermaid-diagrams` - Create and validate Mermaid diagrams
- `zod-schema` - Zod schema patterns for API validation and type inference
- `zod-form-resolver` - React Hook Form + Zod + Shadcn UI form patterns
- `zod-api-hook` - API hooks with Zod validation and toast notifications
```

**Step 2: Verify the changes**

Run: `grep -A7 "Skills Available" .claude/CLAUDE.md`
Expected: Shows all five skills listed

**Step 3: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: add Zod skills to CLAUDE.md"
```

---

## Task 6: Final Verification

**Step 1: Verify all skill files exist**

Run: `ls -la .claude/skills/`
Expected: Shows 4 skill files (visual-debugging.md, mermaid-diagrams.md, zod-schema.md, zod-form-resolver.md, zod-api-hook.md)

**Step 2: Verify agent was updated**

Run: `grep -c "zod-schema\|zod-form-resolver\|zod-api-hook" .claude/agents/typescript-frontend.md`
Expected: Returns 6 or more (multiple references to each skill)

**Step 3: Run git status**

Run: `git status`
Expected: Clean working tree with all changes committed

**Step 4: Review commit history**

Run: `git log --oneline -5`
Expected: Shows 5 commits for this implementation
