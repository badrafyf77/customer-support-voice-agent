import { DashboardWelcomeCard } from '@/components/dashboard/landing/components/dashboard-welcome-card';
import { DashboardQuickActionsCard } from '@/components/dashboard/landing/components/dashboard-quick-actions-card';
import { DashboardRecentExamsCard } from '@/components/dashboard/landing/components/dashboard-recent-exams-card';
import { DashboardSubscriptionCardGroup } from '@/components/dashboard/landing/components/dashboard-subscription-card-group';
import { DashboardTutorialCard } from '@/components/dashboard/landing/components/dashboard-tutorial-card';

export function DashboardLandingPage() {
  return (
    <div className={'grid flex-1 items-start gap-6 p-0 md:grid-cols-1 lg:grid-cols-2 xl:grid-cols-3'}>
      <div className={'grid auto-rows-max items-start gap-6 lg:col-span-2'}>
        <DashboardWelcomeCard />
        <DashboardQuickActionsCard />
        <DashboardRecentExamsCard />
      </div>
      <div className={'grid auto-rows-max items-start gap-6'}>
        <DashboardSubscriptionCardGroup />
        <DashboardTutorialCard />
      </div>
    </div>
  );
}
