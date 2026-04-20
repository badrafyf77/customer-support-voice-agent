import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import { createEvaluatorContestation } from '@/features/exams/server/evaluator-agent';
import { getExamAttemptByIdForUser, getExamContextForUser, requireAuthenticatedUser, resolveExamServiceError } from '@/features/exams/server/exam-service';
import { createClient as createAdminClient } from '@/utils/supabase/server-internal';
import { createClient as createSessionClient } from '@/utils/supabase/server';

interface ContestBody {
  questionId?: unknown;
  question_id?: unknown;
  studentJustification?: unknown;
  student_justification?: unknown;
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const adminSupabase = (await createAdminClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const context = await getExamContextForUser(adminSupabase, user.id);
    const { id: attemptId } = await params;
    const attemptResponse = await getExamAttemptByIdForUser(adminSupabase, user.id, attemptId);

    if (context.role !== 'student' || attemptResponse.attempt.student_user_id !== user.id) {
      return NextResponse.json({ error: 'Only the student who owns this attempt can send a reclamation.' }, { status: 403 });
    }

    const body = ((await request.json().catch(() => ({}))) as ContestBody) || {};
    const questionId = typeof (body.questionId ?? body.question_id) === 'string' ? String(body.questionId ?? body.question_id).trim() : '';
    const studentJustification =
      typeof (body.studentJustification ?? body.student_justification) === 'string'
        ? String(body.studentJustification ?? body.student_justification).trim()
        : '';

    if (!questionId || !studentJustification) {
      return NextResponse.json({ error: 'questionId and studentJustification are required.' }, { status: 400 });
    }

    const result = await createEvaluatorContestation(attemptId, {
      question_id: questionId,
      student_justification: studentJustification,
    });

    return NextResponse.json({
      success: true,
      evaluationId: result.evaluation_id,
      reEvalRequest: result.re_eval_request,
      notificationSent: result.notification_sent === true,
      publishStatus: typeof result.publish_status === 'string' ? result.publish_status : undefined,
      message:
        result.notification_sent === true
          ? 'Reclamation submitted and your teacher was notified by email.'
          : 'Reclamation submitted. Your teacher can still review it from the evaluation dashboard.',
    });
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'POST /api/attempts/[id]/contest');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
