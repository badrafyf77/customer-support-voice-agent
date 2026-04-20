import { Suspense } from 'react';
import { DashboardPageHeader } from '@/components/dashboard/layout/dashboard-page-header';
import { LoadingScreen } from '@/components/dashboard/layout/loading-screen';
import { ExamAttemptDetail } from '@/features/exams/components/exam-attempt-detail';

export default async function ExamAttemptDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return (
    <main className="flex flex-1 flex-col gap-4 p-4 lg:gap-6 lg:p-8">
      <DashboardPageHeader pageTitle="Attempt Detail" />
      <Suspense fallback={<LoadingScreen />}>
        <ExamAttemptDetail attemptId={id} />
      </Suspense>
    </main>
  );
}
