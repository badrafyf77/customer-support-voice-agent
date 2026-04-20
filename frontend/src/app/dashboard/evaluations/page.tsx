import { Suspense } from 'react';
import { DashboardPageHeader } from '@/components/dashboard/layout/dashboard-page-header';
import { LoadingScreen } from '@/components/dashboard/layout/loading-screen';
import { EvaluationsDashboard } from '@/features/exams/components/evaluations-dashboard';

export default function EvaluationsPage() {
  return (
    <main className="flex flex-1 flex-col gap-4 p-4 lg:gap-6 lg:p-8">
      <DashboardPageHeader pageTitle="Evaluations" />
      <Suspense fallback={<LoadingScreen />}>
        <EvaluationsDashboard />
      </Suspense>
    </main>
  );
}
