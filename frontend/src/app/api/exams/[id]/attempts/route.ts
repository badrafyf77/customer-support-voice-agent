import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import {
  getExamAttemptsForUser,
  parseExamPagination,
  requireAuthenticatedUser,
  resolveExamServiceError,
  startExamAttemptForStudent,
} from '@/features/exams/server/exam-service';
import { createClient as createSessionClient } from '@/utils/supabase/server';

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const { id: examId } = await params;
    const { searchParams } = new URL(request.url);
    const pagination = parseExamPagination(searchParams);
    const attempts = await getExamAttemptsForUser(sessionSupabase, user.id, examId, pagination);
    return NextResponse.json(attempts);
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'GET /api/exams/[id]/attempts');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const { id: examId } = await params;
    const body = await request.json().catch(() => ({}));
    const result = await startExamAttemptForStudent(sessionSupabase, user.id, examId, body);

    return NextResponse.json({
      success: true,
      exam: result.exam,
      attempt: result.attempt,
      reused: result.reused,
      message: result.reused ? 'Reusing existing in-progress attempt' : 'Exam attempt started successfully',
    });
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'POST /api/exams/[id]/attempts');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
