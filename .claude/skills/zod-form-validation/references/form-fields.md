# Form Field Components

Shadcn UI form field patterns for common input types.

## Required Imports

```typescript
import { Form, FormField, FormItem, FormLabel, FormControl, FormMessage, FormDescription } from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '~/components/ui/select';
import { Checkbox } from '~/components/ui/checkbox';
import { Textarea } from '~/components/ui/textarea';
import { Button } from '~/components/ui/button';
```

## Text Input

```typescript
<FormField
  control={form.control}
  name="username"
  render={({ field }) => (
    <FormItem>
      <FormLabel>Username</FormLabel>
      <FormControl>
        <Input placeholder="Enter username" {...field} />
      </FormControl>
      <FormDescription>Your display name.</FormDescription>
      <FormMessage />
    </FormItem>
  )}
/>
```

## Email Input

```typescript
<FormField
  control={form.control}
  name="email"
  render={({ field }) => (
    <FormItem>
      <FormLabel>Email</FormLabel>
      <FormControl>
        <Input type="email" placeholder="email@example.com" {...field} />
      </FormControl>
      <FormMessage />
    </FormItem>
  )}
/>
```

## Password Input

```typescript
<FormField
  control={form.control}
  name="password"
  render={({ field }) => (
    <FormItem>
      <FormLabel>Password</FormLabel>
      <FormControl>
        <Input type="password" {...field} />
      </FormControl>
      <FormMessage />
    </FormItem>
  )}
/>
```

## Number Input

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

## Textarea

```typescript
<FormField
  control={form.control}
  name="description"
  render={({ field }) => (
    <FormItem>
      <FormLabel>Description</FormLabel>
      <FormControl>
        <Textarea placeholder="Enter description" {...field} />
      </FormControl>
      <FormMessage />
    </FormItem>
  )}
/>
```

## Select (String Values)

```typescript
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
          <SelectItem value="user">User</SelectItem>
          <SelectItem value="admin">Admin</SelectItem>
          <SelectItem value="moderator">Moderator</SelectItem>
        </SelectContent>
      </Select>
      <FormMessage />
    </FormItem>
  )}
/>
```

## Select (Number Values)

DTX position forms use number values. Convert strings to numbers:

```typescript
<FormField
  control={form.control}
  name="positions.carry"
  render={({ field }) => (
    <FormItem>
      <FormLabel>Carry</FormLabel>
      <Select
        onValueChange={(value) => field.onChange(Number(value))}
        defaultValue={field.value?.toString()}
      >
        <FormControl>
          <SelectTrigger>
            <SelectValue placeholder="Select skill level" />
          </SelectTrigger>
        </FormControl>
        <SelectContent>
          <SelectItem value="1">1 - Beginner</SelectItem>
          <SelectItem value="2">2 - Novice</SelectItem>
          <SelectItem value="3">3 - Intermediate</SelectItem>
          <SelectItem value="4">4 - Advanced</SelectItem>
          <SelectItem value="5">5 - Expert</SelectItem>
        </SelectContent>
      </Select>
      <FormMessage />
    </FormItem>
  )}
/>
```

## Checkbox

```typescript
<FormField
  control={form.control}
  name="isActive"
  render={({ field }) => (
    <FormItem className="flex flex-row items-start space-x-3 space-y-0">
      <FormControl>
        <Checkbox checked={field.value} onCheckedChange={field.onChange} />
      </FormControl>
      <div className="space-y-1 leading-none">
        <FormLabel>Active</FormLabel>
        <FormDescription>Enable this option.</FormDescription>
      </div>
    </FormItem>
  )}
/>
```

## Date Picker

```typescript
import { Calendar } from '~/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '~/components/ui/popover';
import { CalendarIcon } from 'lucide-react';
import { format } from 'date-fns';

<FormField
  control={form.control}
  name="startDate"
  render={({ field }) => (
    <FormItem className="flex flex-col">
      <FormLabel>Date</FormLabel>
      <Popover>
        <PopoverTrigger asChild>
          <FormControl>
            <Button variant="outline" className="w-full justify-start text-left font-normal">
              <CalendarIcon className="mr-2 h-4 w-4" />
              {field.value ? format(field.value, 'PPP') : <span>Pick a date</span>}
            </Button>
          </FormControl>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0">
          <Calendar mode="single" selected={field.value} onSelect={field.onChange} />
        </PopoverContent>
      </Popover>
      <FormMessage />
    </FormItem>
  )}
/>
```

## Multi-Select / Checkbox Group

```typescript
const items = [
  { id: 'carry', label: 'Carry' },
  { id: 'mid', label: 'Mid' },
  { id: 'offlane', label: 'Offlane' },
];

<FormField
  control={form.control}
  name="roles"
  render={() => (
    <FormItem>
      <FormLabel>Preferred Roles</FormLabel>
      <div className="space-y-2">
        {items.map((item) => (
          <FormField
            key={item.id}
            control={form.control}
            name="roles"
            render={({ field }) => (
              <FormItem className="flex items-center space-x-2">
                <FormControl>
                  <Checkbox
                    checked={field.value?.includes(item.id)}
                    onCheckedChange={(checked) => {
                      return checked
                        ? field.onChange([...field.value, item.id])
                        : field.onChange(field.value?.filter((val) => val !== item.id));
                    }}
                  />
                </FormControl>
                <FormLabel className="font-normal">{item.label}</FormLabel>
              </FormItem>
            )}
          />
        ))}
      </div>
      <FormMessage />
    </FormItem>
  )}
/>
```

## Grid Layouts

### Two Columns

```typescript
<div className="grid grid-cols-2 gap-4">
  <FormField control={form.control} name="firstName" ... />
  <FormField control={form.control} name="lastName" ... />
</div>
```

### Five Columns (Position Form)

```typescript
<div className="grid grid-cols-5 gap-4">
  <FormField control={form.control} name="positions.carry" ... />
  <FormField control={form.control} name="positions.mid" ... />
  <FormField control={form.control} name="positions.offlane" ... />
  <FormField control={form.control} name="positions.soft_support" ... />
  <FormField control={form.control} name="positions.hard_support" ... />
</div>
```

## Disabled Fields

```typescript
<FormField
  control={form.control}
  name="steamId"
  render={({ field }) => (
    <FormItem>
      <FormLabel>Steam ID (read-only)</FormLabel>
      <FormControl>
        <Input {...field} disabled />
      </FormControl>
    </FormItem>
  )}
/>
```

## Conditional Fields

```typescript
const watchType = form.watch('type');

{watchType === 'business' && (
  <FormField
    control={form.control}
    name="businessName"
    render={({ field }) => (
      <FormItem>
        <FormLabel>Business Name</FormLabel>
        <FormControl>
          <Input {...field} />
        </FormControl>
        <FormMessage />
      </FormItem>
    )}
  />
)}
```

## Form Actions

```typescript
<div className="flex gap-2">
  <Button type="submit" disabled={form.formState.isSubmitting}>
    {form.formState.isSubmitting ? 'Saving...' : 'Save'}
  </Button>
  <Button type="button" variant="outline" onClick={() => form.reset()}>
    Reset
  </Button>
</div>
```
