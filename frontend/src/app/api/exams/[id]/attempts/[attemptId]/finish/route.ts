import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import {
  finishExamAttemptForUser,
  requireAuthenticatedUser,
  resolveExamServiceError,
} from '@/features/exams/server/exam-service';
import { createClient as createSessionClient } from '@/utils/supabase/server';

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string; attemptId: string }> }) {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const { id: examId, attemptId } = await params;
    const body = await request.json();
    const attempt = await finishExamAttemptForUser(sessionSupabase, user.id, examId, attemptId, body);
    const message =
      attempt.status === 'submitted' ? 'Exam attempt submitted successfully.' : 'Exam attempt updated successfully';

    return NextResponse.json({
      success: true,
      attempt,
      message,
    });
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'POST /api/exams/[id]/attempts/[attemptId]/finish');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
