import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import { requireAuthenticatedUser, resolveExamServiceError } from '@/features/exams/server/exam-service';
import { triggerEvaluatorAttempt } from '@/features/exams/server/evaluator-agent';
import { createClient as createSessionClient } from '@/utils/supabase/server';

interface EvaluateAttemptBody {
  examId?: unknown;
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const { id: attemptId } = await params;

    const body = ((await request.json().catch(() => ({}))) as EvaluateAttemptBody) || {};
    const examId = typeof body.examId === 'string' && body.examId.trim().length > 0 ? body.examId.trim() : undefined;

    const evaluatorResponse = await triggerEvaluatorAttempt({
      attemptId,
      examId,
      triggeredByUserId: user.id,
    });

    return NextResponse.json({
      success: true,
      message: 'Evaluator agent trigger request sent.',
      triggered: evaluatorResponse.accepted,
      evaluator: evaluatorResponse,
    });
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'POST /api/attempts/[id]/evaluate');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
