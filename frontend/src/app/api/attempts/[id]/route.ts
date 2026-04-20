import { NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import {
  ExamServiceError,
  getExamAttemptByIdForUser,
  requireAuthenticatedUser,
  resolveExamServiceError,
} from '@/features/exams/server/exam-service';
import { createClient as createAdminClient } from '@/utils/supabase/server-internal';
import { createClient as createSessionClient } from '@/utils/supabase/server';

function toNumber(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  return null;
}

function toEvaluationQuestionResult(resultRow: Record<string, unknown>) {
  const teacherAdjustedScore = toNumber(resultRow.teacher_adjusted_score);
  const reEvalScore = toNumber(resultRow.re_eval_score);
  const score = toNumber(resultRow.score);
  const effectiveScore = teacherAdjustedScore ?? reEvalScore ?? score ?? 0;
  const feedback =
    (typeof resultRow.feedback === 'string' ? resultRow.feedback : '') ||
    (typeof resultRow.re_eval_feedback === 'string' ? resultRow.re_eval_feedback : '') ||
    (typeof resultRow.teacher_comment === 'string' ? resultRow.teacher_comment : '') ||
    '';
  const effectiveSource =
    teacherAdjustedScore != null ? 'teacher_adjusted' : reEvalScore != null ? 're_evaluated' : 'original';

  return {
    ...resultRow,
    effective_score: effectiveScore,
    effective_feedback: feedback,
    effective_source: effectiveSource,
  };
}

function buildFallbackScoreSummary(
  questionResults: Array<Record<string, unknown>>,
  fallbackOverallScore: number | null,
) {
  if (questionResults.length > 0) {
    const totalScore = questionResults.reduce((sum, row) => {
      const value = toNumber(row.effective_score);
      return sum + (value ?? 0);
    }, 0);

    const maxTotalScore = questionResults.reduce((sum, row) => {
      const value = toNumber(row.max_points);
      return sum + (value ?? 0);
    }, 0);

    return {
      total_score: Number(totalScore.toFixed(2)),
      max_total_score: Number(maxTotalScore.toFixed(2)),
      percentage: maxTotalScore > 0 ? Number(((totalScore / maxTotalScore) * 100).toFixed(2)) : 0,
    };
  }

  if (fallbackOverallScore != null) {
    return {
      total_score: fallbackOverallScore,
      max_total_score: 100,
      percentage: fallbackOverallScore,
    };
  }

  return null;
}

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const adminSupabase = (await createAdminClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const { id: attemptId } = await params;

    // Keep attempt detail fully local so the page remains available even if the evaluator service is restarting.
    const fallbackAttempt = await getExamAttemptByIdForUser(adminSupabase, user.id, attemptId);

    const [questionsResult, questionResultsResult, reEvalRequestsResult, profilesResult] = await Promise.all([
      adminSupabase
        .from('exam_questions')
        .select('*')
        .eq('exam_id', fallbackAttempt.exam.id)
        .order('question_order', { ascending: true }),
      adminSupabase
        .from('exam_question_results')
        .select('*')
        .eq('attempt_id', fallbackAttempt.attempt.id)
        .order('question_order', { ascending: true })
        .order('created_at', { ascending: true }),
      adminSupabase
        .from('re_eval_requests')
        .select('*')
        .eq('attempt_id', fallbackAttempt.attempt.id)
        .order('created_at', { ascending: false }),
      adminSupabase
        .from('profiles')
        .select('*')
        .in('user_id', [fallbackAttempt.attempt.student_user_id, fallbackAttempt.exam.teacher_user_id]),
    ]);

    if (questionsResult.error) {
      throw new ExamServiceError('Failed to load exam questions', 500);
    }

    if (questionResultsResult.error) {
      throw new ExamServiceError('Failed to load question results', 500);
    }

    if (reEvalRequestsResult.error) {
      throw new ExamServiceError('Failed to load re-evaluation requests', 500);
    }

    if (profilesResult.error) {
      throw new ExamServiceError('Failed to load attempt participant profiles', 500);
    }

    const questionResults = (questionResultsResult.data ?? []).map((row) =>
      toEvaluationQuestionResult(row as unknown as Record<string, unknown>),
    );
    const profilesByUserId = new Map((profilesResult.data ?? []).map((profile) => [profile.user_id, profile]));

    return NextResponse.json({
      exam: fallbackAttempt.exam,
      criteria: fallbackAttempt.criteria,
      attempt: fallbackAttempt.attempt,
      questions: questionsResult.data ?? [],
      questionResults,
      reEvalRequests: reEvalRequestsResult.data ?? [],
      studentProfile: profilesByUserId.get(fallbackAttempt.attempt.student_user_id) ?? null,
      teacherProfile: profilesByUserId.get(fallbackAttempt.exam.teacher_user_id) ?? null,
      scoreSummary: buildFallbackScoreSummary(questionResults, fallbackAttempt.attempt.overall_score),
    });
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'GET /api/attempts/[id]');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
