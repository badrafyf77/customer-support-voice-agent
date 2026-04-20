import { NextRequest, NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import { createClient as createSessionClient } from '@/utils/supabase/server';
import { readUpstreamResponse } from '../../upstream-response';

const GENERATE_TIMEOUT_MS = 120_000; // 120 s — LLM calls can be slow

interface GenerateRequestBody {
  topic?: string;
  n_questions?: number;
  question_type?: 'mcq' | 'open' | 'mixed';
  course_id?: string;
  k?: number;
  max_points?: number;
}

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
      .select('teacher_user_id, subject')
      .eq('id', examId)
      .maybeSingle();

    if (examError || !exam) {
      return NextResponse.json({ error: 'Exam not found.' }, { status: 404 });
    }

    if (exam.teacher_user_id !== user.id) {
      return NextResponse.json({ error: 'Forbidden.' }, { status: 403 });
    }

    // ── Proxy to ExamGenerator ───────────────────────────────────────────────
    const body = (await request.json()) as GenerateRequestBody;
    const topic = body.topic?.trim() || exam.subject?.trim() || '';

    if (!topic) {
      return NextResponse.json(
        { error: 'A topic is required to generate questions. Add an exam subject or pass topic explicitly.' },
        { status: 400 },
      );
    }

    const payload = {
      ...body,
      exam_id: examId,
      topic,
      course_id: body.course_id ?? examId,
      question_type: body.question_type ?? 'mixed',
      k: body.k ?? 5,
    };

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), GENERATE_TIMEOUT_MS);

    try {
      const response = await fetch(`${examGeneratorUrl}/generate`, {
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
      return NextResponse.json({ error: 'Question generation timed out after 120 seconds.' }, { status: 504 });
    }
    const message = error instanceof Error ? error.message : 'Generate proxy failed.';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
