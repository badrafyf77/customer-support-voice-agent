import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import { rejectEvaluatorReEvalRequest } from '@/features/exams/server/evaluator-agent';
import { getExamAttemptByIdForUser, getExamContextForUser, requireAuthenticatedUser, resolveExamServiceError } from '@/features/exams/server/exam-service';
import { createClient as createAdminClient } from '@/utils/supabase/server-internal';
import { createClient as createSessionClient } from '@/utils/supabase/server';

interface RejectBody {
  reason?: unknown;
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
      return NextResponse.json({ error: 'Only the teacher who owns this exam can reject re-evaluations.' }, { status: 403 });
    }

    const body = ((await request.json().catch(() => ({}))) as RejectBody) || {};
    const reason = typeof body.reason === 'string' ? body.reason.trim() : '';
    if (!reason) {
      return NextResponse.json({ error: 'reason is required.' }, { status: 400 });
    }

    const result = await rejectEvaluatorReEvalRequest(requestId, { reason });

    return NextResponse.json({
      success: true,
      reEvalRequest: result.re_eval_request,
      message: 'Re-evaluation request rejected successfully.',
    });
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'POST /api/re-eval-requests/[id]/reject');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
