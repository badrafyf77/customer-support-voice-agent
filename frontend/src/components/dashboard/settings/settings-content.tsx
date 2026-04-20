'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ProfileSettings } from './profile-settings';
import { AccountSettings } from './account-settings';

export function SettingsContent() {
  return (
    <Tabs defaultValue="profile" className="w-full">
      <TabsList className="grid w-full max-w-md grid-cols-2">
        <TabsTrigger value="profile">Profile</TabsTrigger>
        <TabsTrigger value="account">Account</TabsTrigger>
      </TabsList>

      <TabsContent value="profile" className="mt-6">
        <ProfileSettings />
      </TabsContent>

      <TabsContent value="account" className="mt-6">
        <AccountSettings />
      </TabsContent>
    </Tabs>
  );
}
