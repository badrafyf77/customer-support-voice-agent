import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import { createClient as createSessionClient } from '@/utils/supabase/server';
import { readUpstreamResponse } from '../../upstream-response';

const UPLOAD_TIMEOUT_MS = 60_000; // 60 s — generous for large PDFs

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  // ── Runtime env check (not module-level so it never crashes the whole app) ──
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
    const formData = await request.formData();
    if (!formData.has('course_id')) {
      formData.set('course_id', examId);
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);

    try {
      const response = await fetch(`${examGeneratorUrl}/upload`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });

      const data = await readUpstreamResponse(response);
      return NextResponse.json(data, { status: response.status });
    } finally {
      clearTimeout(timer);
    }
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json({ error: 'Upload timed out after 60 seconds.' }, { status: 504 });
    }
    const message = error instanceof Error ? error.message : 'Upload proxy failed.';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
