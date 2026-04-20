import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import { adjustEvaluatorQuestion } from '@/features/exams/server/evaluator-agent';
import { getExamAttemptByIdForUser, getExamContextForUser, requireAuthenticatedUser, resolveExamServiceError } from '@/features/exams/server/exam-service';
import { createClient as createAdminClient } from '@/utils/supabase/server-internal';
import { createClient as createSessionClient } from '@/utils/supabase/server';

interface AdjustmentBody {
  adjustedScore?: unknown;
  adjusted_score?: unknown;
  comment?: unknown;
}

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string; questionId: string }> }) {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const adminSupabase = (await createAdminClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const context = await getExamContextForUser(adminSupabase, user.id);
    const { id: attemptId, questionId } = await params;
    const attemptResponse = await getExamAttemptByIdForUser(adminSupabase, user.id, attemptId);

    if (!(context.role === 'teacher' || context.role === 'admin') || attemptResponse.exam.teacher_user_id !== user.id) {
      return NextResponse.json({ error: 'Only the teacher who owns this exam can adjust question scores.' }, { status: 403 });
    }

    const body = ((await request.json().catch(() => ({}))) as AdjustmentBody) || {};
    const adjustedScoreValue = body.adjustedScore ?? body.adjusted_score;
    const adjustedScore = typeof adjustedScoreValue === 'number' ? adjustedScoreValue : Number(adjustedScoreValue);
    const comment = typeof body.comment === 'string' ? body.comment.trim() : '';

    if (!Number.isFinite(adjustedScore)) {
      return NextResponse.json({ error: 'adjustedScore must be a valid number.' }, { status: 400 });
    }

    const result = await adjustEvaluatorQuestion(attemptId, questionId, {
      adjusted_score: adjustedScore,
      comment: comment || undefined,
    });

    return NextResponse.json({
      success: true,
      evaluationId: result.evaluation_id,
      questionResult: result.question_result,
      attempt: result.attempt,
      scoreSummary: result.score_summary,
      message: 'Question score adjusted successfully.',
    });
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'PATCH /api/attempts/[id]/questions/[questionId]');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
