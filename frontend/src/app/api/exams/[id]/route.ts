import { NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import {
  getExamByIdForUser,
  requireAuthenticatedUser,
  resolveExamServiceError,
} from '@/features/exams/server/exam-service';
import { createClient as createSessionClient } from '@/utils/supabase/server';

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const { id: examId } = await params;
    const examDetail = await getExamByIdForUser(sessionSupabase, user.id, examId);
    return NextResponse.json(examDetail);
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'GET /api/exams/[id]');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
