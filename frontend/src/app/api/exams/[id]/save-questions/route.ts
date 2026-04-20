import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import { createClient as createSessionClient } from '@/utils/supabase/server';
import { readUpstreamResponse } from '../../upstream-response';

const SAVE_TIMEOUT_MS = 30_000; // 30 s

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const examGeneratorUrl = process.env.EXAM_GENERATOR_URL;
  if (!examGeneratorUrl) {
    return NextResponse.json({ error: 'Exam generator service is not configured on this server.' }, { status: 503 });
  }

  try {
    // ── Auth ─────────────────────────────────────────────────────────────────
    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const {
      data: { user },
      error: authError,
    } = await sessionSupabase.auth.getUser();

    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // ── Ownership check ──────────────────────────────────────────────────────
    const { id: examId } = await params;
    const { data: exam, error: examError } = await sessionSupabase
      .from('exams')
      .select('teacher_user_id')
      .eq('id', examId)
      .maybeSingle();

    if (examError || !exam) {
      return NextResponse.json({ error: 'Exam not found.' }, { status: 404 });
    }

    if (exam.teacher_user_id !== user.id) {
      return NextResponse.json({ error: 'Forbidden.' }, { status: 403 });
    }

    // ── Proxy to ExamGenerator ───────────────────────────────────────────────
    const body = (await request.json()) as Record<string, unknown>;
    const payload = { ...body, exam_id: examId };

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), SAVE_TIMEOUT_MS);

    try {
      const response = await fetch(`${examGeneratorUrl}/save-questions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      const data = await readUpstreamResponse(response);
      return NextResponse.json(data, { status: response.status });
    } finally {
      clearTimeout(timer);
    }
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json({ error: 'Save timed out after 30 seconds.' }, { status: 504 });
    }
    const message = error instanceof Error ? error.message : 'Save proxy failed.';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
