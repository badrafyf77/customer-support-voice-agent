import { DashboardPageHeader } from '@/components/dashboard/layout/dashboard-page-header';
import { SettingsContent } from '@/components/dashboard/settings/settings-content';
import { LoadingScreen } from '@/components/dashboard/layout/loading-screen';
import { Suspense } from 'react';

export default function SettingsPage() {
  return (
    <main className="flex flex-1 flex-col gap-4 p-4 lg:gap-6 lg:p-8">
      <DashboardPageHeader pageTitle="Settings" />
      <Suspense fallback={<LoadingScreen />}>
        <SettingsContent />
      </Suspense>
    </main>
  );
}
