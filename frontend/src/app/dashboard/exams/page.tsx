import { Suspense } from 'react';
import { DashboardPageHeader } from '@/components/dashboard/layout/dashboard-page-header';
import { LoadingScreen } from '@/components/dashboard/layout/loading-screen';
import { ExamWorkspace } from '@/features/exams/components/exam-workspace';

export default function ExamsPage() {
  return (
    <main className="flex flex-1 flex-col gap-4 p-4 lg:gap-6 lg:p-8">
      <DashboardPageHeader pageTitle="Exam Workspace" />
      <Suspense fallback={<LoadingScreen />}>
        <ExamWorkspace />
      </Suspense>
    </main>
  );
}
