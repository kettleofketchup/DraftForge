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
