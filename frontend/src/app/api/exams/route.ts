import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import {
  createExamForTeacher,
  listExamsForUser,
  parseExamPagination,
  requireAuthenticatedUser,
  resolveExamServiceError,
} from '@/features/exams/server/exam-service';
import { createClient as createSessionClient } from '@/utils/supabase/server';

export async function GET(request: NextRequest) {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const { searchParams } = new URL(request.url);
    const pagination = parseExamPagination(searchParams);
    const exams = await listExamsForUser(sessionSupabase, user.id, pagination);
    return NextResponse.json(exams);
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'GET /api/exams');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}

export async function POST(request: NextRequest) {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const body = await request.json();
    const { exam, criteria } = await createExamForTeacher(sessionSupabase, user.id, body);

    return NextResponse.json({
      success: true,
      exam,
      criteria,
      message: 'Exam created successfully',
    });
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'POST /api/exams');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
