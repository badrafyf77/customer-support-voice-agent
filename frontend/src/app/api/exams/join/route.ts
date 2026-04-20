import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import {
  joinExamForStudent,
  requireAuthenticatedUser,
  resolveExamServiceError,
} from '@/features/exams/server/exam-service';
import { createClient as createSessionClient } from '@/utils/supabase/server';

export async function POST(request: NextRequest) {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const body = await request.json();
    const result = await joinExamForStudent(sessionSupabase, user.id, body);

    return NextResponse.json({
      success: true,
      exam: result.exam,
      enrollment: result.enrollment,
      alreadyJoined: result.alreadyJoined,
      message: result.alreadyJoined ? 'You were already enrolled in this exam' : 'Joined exam successfully',
    });
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'POST /api/exams/join');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
