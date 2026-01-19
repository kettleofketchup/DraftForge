import React, { useEffect } from 'react';
import type { UserType } from '~/components/user';
import { useUserStore } from '~/store/userStore';

import { useState } from 'react';
import { getLogger } from '~/lib/logger';
const log = getLogger('Position Edit');

import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { z } from 'zod';

import { UpdateProfile } from '~/components/api/api';
import { Button } from '~/components/ui/button';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '~/components/ui/form';
import { Input } from '~/components/ui/input';
import { UserSchema } from '~/components/user/schemas';
import { PositionForm } from './forms/position';
export const ProfilePage: React.FC = () => {
  const currentUser = useUserStore((state) => state.currentUser);
  const setCurrentUser = useUserStore((state) => state.setCurrentUser);
  const form = useForm<z.infer<typeof UserSchema>>({
    resolver: zodResolver(UserSchema),
    defaultValues: {
      positions: {
        ...currentUser?.positions,
      },
    },
  });

  const [errorMessage, setErrorMessage] = useState<
    Partial<Record<keyof UserType, string>>
  >({});
  const setUser = useUserStore((state) => state.setUser);

  const initialiazeForm = () => {
    if (currentUser == null || currentUser == undefined) return;

    form.setValue('positions.carry', currentUser?.positions?.carry || 0);
    form.setValue('positions.mid', currentUser?.positions?.mid || 0);
    form.setValue('positions.offlane', currentUser?.positions?.offlane || 0);
    form.setValue(
      'positions.soft_support',
      currentUser?.positions?.soft_support || 0,
    );
    form.setValue(
      'positions.hard_support',
      currentUser?.positions?.hard_support || 0,
    );
    form.setValue('steamid', currentUser?.steamid || null);
    log.debug('Form initialized with values:', form.getValues());
    log.debug(currentUser);
  };

  useEffect(() => {
    initialiazeForm();
  }, [currentUser, form]);

  if (!currentUser) {
    return (
      <div className="flex justify-center items-center h-screen">
        Not logged in
      </div>
    );
  }

  function onSubmit(data: z.infer<typeof UserSchema>) {
    toast.promise(UpdateProfile(data), {
      loading: 'Updating...',
      success: (data: UserType) => {
        setUser(data);
        setCurrentUser(data);
        return 'You submitted the following values';
      },
      error: 'Failed to update user',
      description: (
        <pre className="mt-2 w-[320px] rounded-md bg-neutral-950 p-4">
          <code className="text-white">{JSON.stringify(data, null, 2)}</code>
        </pre>
      ),
    });
  }

  return (
    <div className="container px-1 sm:mx-auto sm:p-4">
      <div className="flex flex-col  gap-4">
        <div className="flex flex-col  sm:flex-row w-90 justify-center text-center align-center w-full">
          <h1 className="text-title text-pretty text-center">
            {currentUser.username}
          </h1>
        </div>

        <div className="flex-1 w-full justify-center align-center self-center ">
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="">
              <PositionForm form={form} />

              <FormField
                control={form.control}
                name="steamid"
                rules={{
                  validate: (value) => {
                    if (currentUser?.steamid && !value) {
                      return 'Steam ID cannot be cleared once set';
                    }
                    return true;
                  },
                }}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Steam ID</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        placeholder="Enter your Steam ID"
                        {...field}
                        value={field.value ?? ''}
                        onChange={(e) => {
                          const val = e.target.value;
                          field.onChange(val ? parseInt(val, 10) : null);
                        }}
                      />
                    </FormControl>
                    {currentUser?.steamid && (
                      <FormDescription>
                        Steam ID cannot be removed once set
                      </FormDescription>
                    )}
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex justify-center align-center self-center">
                <Button type="submit">Submit</Button>
              </div>
            </form>
          </Form>
        </div>
      </div>
    </div>
  );
};
