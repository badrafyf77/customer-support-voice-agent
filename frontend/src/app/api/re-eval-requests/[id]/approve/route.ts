import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import { approveEvaluatorReEvalRequest } from '@/features/exams/server/evaluator-agent';
import { getExamAttemptByIdForUser, getExamContextForUser, requireAuthenticatedUser, resolveExamServiceError } from '@/features/exams/server/exam-service';
import { createClient as createAdminClient } from '@/utils/supabase/server-internal';
import { createClient as createSessionClient } from '@/utils/supabase/server';

interface ApproveBody {
  teacherResponse?: unknown;
  teacher_response?: unknown;
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const adminSupabase = (await createAdminClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const context = await getExamContextForUser(adminSupabase, user.id);
    const { id: requestId } = await params;

    const { data: reEvalRequest, error } = await adminSupabase
      .from('re_eval_requests')
      .select('id, attempt_id')
      .eq('id', requestId)
      .maybeSingle();

    if (error) {
      throw error;
    }

    if (!reEvalRequest) {
      return NextResponse.json({ error: 'Re-evaluation request not found.' }, { status: 404 });
    }

    const attemptResponse = await getExamAttemptByIdForUser(adminSupabase, user.id, reEvalRequest.attempt_id);
    if (!(context.role === 'teacher' || context.role === 'admin') || attemptResponse.exam.teacher_user_id !== user.id) {
      return NextResponse.json({ error: 'Only the teacher who owns this exam can approve re-evaluations.' }, { status: 403 });
    }

    const body = ((await request.json().catch(() => ({}))) as ApproveBody) || {};
    const teacherResponse =
      typeof (body.teacherResponse ?? body.teacher_response) === 'string'
        ? String(body.teacherResponse ?? body.teacher_response).trim()
        : undefined;

    const result = await approveEvaluatorReEvalRequest(requestId, {
      teacher_response: teacherResponse,
    });

    return NextResponse.json({
      success: true,
      evaluationId: result.evaluation_id,
      reEvalRequest: result.re_eval_request,
      questionResult: result.question_result,
      attempt: result.attempt,
      scoreSummary: result.score_summary,
      message: 'Re-evaluation approved and processed successfully.',
    });
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'POST /api/re-eval-requests/[id]/approve');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
