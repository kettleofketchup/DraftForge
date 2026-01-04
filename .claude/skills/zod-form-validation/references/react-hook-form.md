# React Hook Form Integration

Complete guide for React Hook Form with ZodResolver.

## Setup

```typescript
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm, UseFormReturn } from 'react-hook-form';
import { z } from 'zod';
import { Form } from '~/components/ui/form';
```

## Basic Form Structure

```typescript
const FormSchema = z.object({
  email: z.string().email('Invalid email'),
  password: z.string().min(8, 'At least 8 characters'),
});

type FormData = z.infer<typeof FormSchema>;

export function MyForm() {
  const form = useForm<FormData>({
    resolver: zodResolver(FormSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = (data: FormData) => {
    console.log(data);
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)}>
        {/* FormFields here */}
        <Button type="submit">Submit</Button>
      </form>
    </Form>
  );
}
```

## Form Component Hierarchy

```
<Form {...form}>                    // FormProvider wrapper
  <form onSubmit={form.handleSubmit(onSubmit)}>
    <FormField
      control={form.control}        // Controller wrapper
      name="fieldName"
      render={({ field }) => (
        <FormItem>                  // Container with ID
          <FormLabel>Label</FormLabel>
          <FormControl>             // Slot for input
            <Input {...field} />
          </FormControl>
          <FormDescription>Helper</FormDescription>
          <FormMessage />           // Auto error display
        </FormItem>
      )}
    />
  </form>
</Form>
```

## useForm Configuration

```typescript
const form = useForm<FormData>({
  resolver: zodResolver(FormSchema),
  defaultValues: { email: '', password: '' },
  mode: 'onBlur',        // Validate on blur (default: 'onSubmit')
  reValidateMode: 'onChange',
});
```

### Form Methods

```typescript
form.handleSubmit(onSubmit)  // Submit handler
form.watch('fieldName')      // Watch field changes
form.getValues()             // Get current values
form.setValue('field', val)  // Set field value
form.reset()                 // Reset form
form.trigger('field')        // Trigger validation
```

### Form State

```typescript
form.formState.isDirty       // User changed values
form.formState.isValid       // All fields valid
form.formState.isSubmitting  // During submission
form.formState.errors        // Field errors
```

## Passing Form to Child Components

```typescript
type PositionFormProps = {
  form: UseFormReturn<any, any, any>;
};

export const PositionForm = ({ form }: PositionFormProps) => {
  return (
    <FormField
      control={form.control}
      name="positions.carry"  // Nested field
      render={({ field }) => (
        <FormItem>
          <FormLabel>Carry</FormLabel>
          {/* ... */}
        </FormItem>
      )}
    />
  );
};
```

## Error Handling

### Automatic Display

`<FormMessage />` automatically displays errors:

```typescript
<FormField
  control={form.control}
  name="email"
  render={({ field }) => (
    <FormItem>
      <FormLabel>Email</FormLabel>
      <FormControl>
        <Input {...field} />
      </FormControl>
      <FormMessage />  {/* Shows: "Invalid email" */}
    </FormItem>
  )}
/>
```

### Manual Error Access

```typescript
const { errors } = form.formState;
if (errors.email) {
  console.log(errors.email.message);
}
```

### Form-Level Errors

```typescript
const Schema = z.object({
  password: z.string(),
  confirm: z.string(),
}).refine(data => data.password === data.confirm, {
  message: "Passwords don't match",
  path: ['confirm'],  // Error appears on confirm field
});
```

## Submission Handling

### With Toast Promise (DTX Pattern)

```typescript
import { toast } from 'sonner';
import { getLogger } from '~/lib/logger';

const log = getLogger('MyForm');

const onSubmit = (data: FormData) => {
  toast.promise(apiCall(data), {
    loading: 'Saving...',
    success: (response) => {
      setData(response);
      return 'Saved successfully!';
    },
    error: (err) => {
      log.error('API call failed', err);
      return `Failed: ${err?.response?.data ?? String(err)}`;
    },
  });
};
```

## Nested Fields

```typescript
const Schema = z.object({
  user: z.object({
    name: z.string(),
    address: z.object({
      city: z.string(),
    }),
  }),
});

// Access with dot notation
<FormField control={form.control} name="user.name" ... />
<FormField control={form.control} name="user.address.city" ... />
```

## Array Fields

```typescript
import { useFieldArray } from 'react-hook-form';

const { fields, append, remove } = useFieldArray({
  control: form.control,
  name: 'items',
});

{fields.map((field, index) => (
  <FormField
    key={field.id}
    control={form.control}
    name={`items.${index}.name`}
    render={({ field }) => <Input {...field} />}
  />
))}

<Button onClick={() => append({ name: '' })}>Add</Button>
```

## DTX Reference Implementation

See `~/pages/profile/profile.tsx`:

```typescript
export const ProfilePage: React.FC = () => {
  const currentUser = useUserStore((state) => state.currentUser);

  const form = useForm<z.infer<typeof UserSchema>>({
    resolver: zodResolver(UserSchema),
    defaultValues: {
      positions: { ...currentUser?.positions },
    },
  });

  async function onSubmit(data: z.infer<typeof UserSchema>) {
    toast.promise(UpdateProfile(data), {
      loading: 'Updating...',
      success: (response) => {
        setCurrentUser(response);
        return 'Profile updated!';
      },
      error: (err) => `Failed: ${err?.response?.data ?? String(err)}`,
    });
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)}>
        <PositionForm form={form} />
        <Button type="submit">Save</Button>
      </form>
    </Form>
  );
};
```

## Accessibility (Built-in)

Shadcn form components provide:

```typescript
<input
  id="form-item-{unique-id}"
  aria-describedby="form-item-description form-item-message"
  aria-invalid={!!error}
/>
<label htmlFor="form-item-{unique-id}">...</label>
<p id="form-item-description">Helper text</p>
<p id="form-item-message" class="text-destructive">Error</p>
```
