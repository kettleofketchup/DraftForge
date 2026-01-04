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
