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
import { SubmitButton } from '~/components/ui/buttons';
import { UpdateProfile } from '~/components/api/api';
import { useUserStore } from '~/store/userStore';
import type { UserType } from '~/components/user/types';
import { PositionForm } from '~/pages/profile/forms/position';
import { getLogger } from '~/lib/logger';

const log = getLogger('EditProfileModal');

const EditProfileSchema = z.object({
  nickname: z.string().min(2).max(100).nullable().optional(),
  steam_account_id: z.number().min(0).nullable().optional(),
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
      steam_account_id: user.steam_account_id ?? null,
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
        steam_account_id: user.steam_account_id ?? null,
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
      // Only send fields that the user actually changed
      const { dirtyFields } = form.formState;
      const payload: Partial<EditProfileFormData> = {};
      if (dirtyFields.nickname) payload.nickname = data.nickname;
      if (dirtyFields.steam_account_id) payload.steam_account_id = data.steam_account_id;
      if (dirtyFields.positions) payload.positions = data.positions;

      const updatedUser = await UpdateProfile(payload);
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

            {/* Friend ID (32-bit Steam Account ID) */}
            <FormField
              control={form.control}
              name="steam_account_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Friend ID</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      placeholder="Enter your Friend ID (from Dotabuff)"
                      {...field}
                      value={field.value ?? ''}
                      onChange={(e) => {
                        const val = e.target.value;
                        field.onChange(val ? parseInt(val, 10) : null);
                      }}
                      disabled={!!user.steam_account_id}
                    />
                  </FormControl>
                  <FormDescription>
                    {user.steam_account_id
                      ? 'Friend ID cannot be changed once set'
                      : 'Your Friend ID (found on Dotabuff URL)'}
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
              <SubmitButton
                loading={form.formState.isSubmitting}
                loadingText="Saving..."
              >
                Save Changes
              </SubmitButton>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
