import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog';
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
import { Button } from '~/components/ui/button';
import { UpdateProfile } from '~/components/api/api';
import { useUserStore } from '~/store/userStore';
import type { UserType } from '~/components/user/types';
import { PositionForm } from '~/pages/profile/forms/position';
import { getLogger } from '~/lib/logger';

const log = getLogger('EditProfileModal');

const EditProfileSchema = z.object({
  nickname: z.string().min(2).max(100).nullable().optional(),
  mmr: z.number().min(0).max(20000).nullable().optional(),
  steamid: z.number().min(0).nullable().optional(),
  positions: z.object({
    carry: z.number().min(0),
    mid: z.number().min(0),
    offlane: z.number().min(0),
    soft_support: z.number().min(0),
    hard_support: z.number().min(0),
  }).optional(),
});

type EditProfileFormData = z.infer<typeof EditProfileSchema>;

interface EditProfileModalProps {
  user: UserType;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave?: () => void;
}

export function EditProfileModal({
  user,
  open,
  onOpenChange,
  onSave,
}: EditProfileModalProps) {
  const setCurrentUser = useUserStore((state) => state.setCurrentUser);
  const setUser = useUserStore((state) => state.setUser);

  const form = useForm<EditProfileFormData>({
    resolver: zodResolver(EditProfileSchema),
    defaultValues: {
      nickname: user.nickname ?? '',
      mmr: user.mmr ?? null,
      steamid: user.steamid ?? null,
      positions: {
        carry: user.positions?.carry ?? 0,
        mid: user.positions?.mid ?? 0,
        offlane: user.positions?.offlane ?? 0,
        soft_support: user.positions?.soft_support ?? 0,
        hard_support: user.positions?.hard_support ?? 0,
      },
    },
  });

  // Reset form when user changes or modal opens
  useEffect(() => {
    if (open) {
      form.reset({
        nickname: user.nickname ?? '',
        mmr: user.mmr ?? null,
        steamid: user.steamid ?? null,
        positions: {
          carry: user.positions?.carry ?? 0,
          mid: user.positions?.mid ?? 0,
          offlane: user.positions?.offlane ?? 0,
          soft_support: user.positions?.soft_support ?? 0,
          hard_support: user.positions?.hard_support ?? 0,
        },
      });
    }
  }, [open, user, form]);

  const onSubmit = async (data: EditProfileFormData) => {
    try {
      const updatedUser = await UpdateProfile(data);
      setUser(updatedUser);
      setCurrentUser(updatedUser);
      toast.success('Profile updated successfully');
      onOpenChange(false);
      onSave?.();
    } catch (error) {
      log.error('Failed to update profile', error);
      toast.error('Failed to update profile');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Profile</DialogTitle>
          <DialogDescription>
            Update your profile information
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {/* Nickname */}
            <FormField
              control={form.control}
              name="nickname"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Nickname</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Enter your nickname"
                      {...field}
                      value={field.value ?? ''}
                    />
                  </FormControl>
                  <FormDescription>
                    Display name shown on your profile
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* MMR */}
            <FormField
              control={form.control}
              name="mmr"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Base MMR</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      placeholder="Enter your MMR"
                      {...field}
                      value={field.value ?? ''}
                      onChange={(e) => {
                        const val = e.target.value;
                        field.onChange(val ? parseInt(val, 10) : null);
                      }}
                      disabled
                      className="bg-muted text-muted-foreground"
                    />
                  </FormControl>
                  <FormDescription className="text-amber-600">
                    ⚠️ Only provide your last ranked MMR. Contact an admin to update.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Steam ID */}
            <FormField
              control={form.control}
              name="steamid"
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
                      disabled={!!user.steamid}
                    />
                  </FormControl>
                  <FormDescription>
                    {user.steamid
                      ? 'Steam ID cannot be changed once set'
                      : 'Your Steam account ID (found on Dotabuff)'}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Positions */}
            <div className="pt-2">
              <PositionForm form={form} />
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-2 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
