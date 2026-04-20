import { Suspense } from 'react';
import { DashboardPageHeader } from '@/components/dashboard/layout/dashboard-page-header';
import { LoadingScreen } from '@/components/dashboard/layout/loading-screen';
import { LiveOralExamRoom } from '@/features/exams/components/live-oral-exam-room';

export default async function OralExamRoomPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return (
    <main className="flex flex-1 flex-col gap-4 p-4 lg:gap-6 lg:p-8">
      <DashboardPageHeader pageTitle="Oral Exam Room" />
      <Suspense fallback={<LoadingScreen />}>
        <LiveOralExamRoom attemptId={id} />
      </Suspense>
    </main>
  );
}
