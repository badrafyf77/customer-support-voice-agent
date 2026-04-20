import { NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import {
  getExamContextForUser,
  requireAuthenticatedUser,
  resolveExamServiceError,
} from '@/features/exams/server/exam-service';
import { createClient as createSessionClient } from '@/utils/supabase/server';

export async function GET() {
  try {
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const context = await getExamContextForUser(sessionSupabase, user.id);
    return NextResponse.json(context);
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'GET /api/exams/context');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
