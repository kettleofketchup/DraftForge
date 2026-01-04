# Zod Schema Patterns

Comprehensive reference for Zod schema definitions and validation.

## Basic Types

```typescript
import { z } from 'zod';

// Primitives
const str = z.string();
const num = z.number();
const bool = z.boolean();
const date = z.date();
const literal = z.literal("admin");
```

## String Validation

```typescript
// Length constraints
z.string().min(3, 'Too short').max(100, 'Too long')

// Format validators (Zod 4 standalone style)
z.email('Invalid email')
z.url()
z.uuid()

// Regex patterns
z.string().regex(/^[a-zA-Z0-9_]{3,15}$/, 'Invalid format')

// Transformations
z.string().trim().toLowerCase()
```

## Number Validation

```typescript
z.number().int().min(0).max(150)
z.number().positive()
z.number().negative()
z.number().multipleOf(5)
z.number().finite()
```

## Object Schemas

```typescript
const UserSchema = z.object({
  id: z.number(),
  username: z.string().min(2).max(100),
  email: z.string().email(),
  createdAt: z.date(),
});

type User = z.infer<typeof UserSchema>;
```

## Array Schemas

```typescript
z.array(z.string())           // string[]
z.array(z.string()).nonempty() // At least one
z.array(z.string()).min(1)     // Min 1 item
z.array(z.string()).max(10)    // Max 10 items
z.array(z.string()).length(5)  // Exactly 5
```

## Optional & Nullable

```typescript
z.string().optional()           // string | undefined
z.string().nullable()           // string | null
z.string().optional().nullable() // string | null | undefined

// Default values
z.string().default('unknown')
z.array(z.string()).default(() => [])
```

## Union Types

```typescript
// Simple union
z.union([z.string(), z.number()])
z.string().or(z.boolean())

// Enum
z.enum(['pending', 'completed', 'failed'])

// Discriminated union (better performance)
const Success = z.object({ status: z.literal('success'), data: z.any() });
const Error = z.object({ status: z.literal('error'), message: z.string() });
const Response = z.discriminatedUnion('status', [Success, Error]);
```

## Schema Composition

### Extend

```typescript
const BaseUser = z.object({ name: z.string(), email: z.string().email() });
const AdminUser = BaseUser.extend({ role: z.literal('admin') });
```

### Merge

```typescript
const userBasic = z.object({ id: z.string(), name: z.string() });
const userContact = z.object({ email: z.string().email() });
const completeUser = userBasic.merge(userContact);
```

### Pick & Omit

```typescript
const DBUser = z.object({ id: z.string(), email: z.string(), password: z.string() });
const PublicUser = DBUser.omit({ password: true });
const LoginData = DBUser.pick({ email: true, password: true });
```

### Partial

```typescript
const UpdateUser = UserSchema.partial(); // All fields optional
```

## Custom Refinements

```typescript
// Single refinement
z.string().refine(
  (val) => /[A-Z]/.test(val),
  { message: 'Must contain uppercase' }
)

// Cross-field validation
z.object({
  password: z.string().min(8),
  confirm: z.string()
}).refine(
  (data) => data.password === data.confirm,
  { message: "Passwords don't match", path: ['confirm'] }
)
```

## Error Handling

### Parse (throws)

```typescript
try {
  const data = UserSchema.parse(input);
} catch (error) {
  if (error instanceof z.ZodError) {
    console.log(error.issues);
  }
}
```

### SafeParse (non-throwing)

```typescript
const result = UserSchema.safeParse(input);
if (result.success) {
  console.log(result.data);
} else {
  console.log(result.error.flatten());
}
```

## Coercion (Form Data)

Form inputs always come as strings. Use coercion:

```typescript
z.coerce.number()  // '42' -> 42
z.coerce.date()    // '2024-01-01' -> Date
z.coerce.boolean() // 'true' -> true
```

## DTX Project Examples

### Position Schema

```typescript
export const PositionSchema = z.object({
  pk: z.number().optional(),
  carry: z.number().min(0, { message: 'Carry position must be selected.' }),
  mid: z.number().min(0),
  offlane: z.number().min(0),
  soft_support: z.number().min(0),
  hard_support: z.number().min(0),
});
```

### User Schema

```typescript
export const UserSchema = z.object({
  positions: PositionSchema.optional(),
  username: z.string().min(2).max(100),
  nickname: z.string().min(2).max(100).nullable().optional(),
  mmr: z.number().min(0).nullable().optional(),
  steamid: z.number().min(0).nullable().optional(),
  discordId: z.string().min(2).max(100).nullable().optional(),
});

export type UserType = z.infer<typeof UserSchema>;
```

## API Validation Pattern

```typescript
// Request schema
const CreateUserRequest = z.object({
  username: z.string().min(3),
  email: z.string().email(),
  role: z.enum(['user', 'admin']),
});

// Response schema
const UserResponse = z.object({
  id: z.string().uuid(),
  username: z.string(),
  email: z.string(),
  createdAt: z.string().datetime(),
});

// Validate API response
async function getUser(id: string) {
  const response = await api.get(`/users/${id}`);
  return UserResponse.parse(response.data);
}
```
