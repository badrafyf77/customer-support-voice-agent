import { NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import { fetchStudentEvaluations, fetchTeacherEvaluations } from '@/features/exams/server/evaluator-agent';
import { getExamContextForUser, requireAuthenticatedUser, resolveExamServiceError } from '@/features/exams/server/exam-service';
import { createClient as createAdminClient } from '@/utils/supabase/server-internal';
import { createClient as createSessionClient } from '@/utils/supabase/server';

export async function GET() {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const adminSupabase = (await createAdminClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const context = await getExamContextForUser(adminSupabase, user.id);

    if (!context.role) {
      return NextResponse.json({ role: null, evaluations: [] });
    }

    if (context.role === 'teacher' || context.role === 'admin') {
      const response = await fetchTeacherEvaluations(user.id);
      return NextResponse.json({ role: context.role, evaluations: response.evaluations || [] });
    }

    const response = await fetchStudentEvaluations(user.id);
    return NextResponse.json({ role: context.role, evaluations: response.evaluations || [] });
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'GET /api/evaluations');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
