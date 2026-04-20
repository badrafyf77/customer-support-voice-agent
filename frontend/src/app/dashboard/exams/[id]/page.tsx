import { Suspense } from 'react';
import { DashboardPageHeader } from '@/components/dashboard/layout/dashboard-page-header';
import { LoadingScreen } from '@/components/dashboard/layout/loading-screen';
import { ExamDetail } from '@/features/exams/components/exam-detail';

export default async function ExamDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return (
    <main className="flex flex-1 flex-col gap-4 p-4 lg:gap-6 lg:p-8">
      <DashboardPageHeader pageTitle="Exam Detail" />
      <Suspense fallback={<LoadingScreen />}>
        <ExamDetail examId={id} />
      </Suspense>
    </main>
  );
}
