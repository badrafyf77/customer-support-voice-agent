import { NextResponse } from 'next/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import type { Exam, ExamAttempt, ExamEnrollment, ExamWrittenAnswer } from '@/lib/database.types';
import { triggerEvaluatorAttempt } from '@/features/exams/server/evaluator-agent';
import type { EvaluatorTestScenario } from '@/features/exams/types';
import {
  getExamContextForUser,
  requireAuthenticatedUser,
  resolveExamServiceError,
} from '@/features/exams/server/exam-service';
import { createClient as createAdminClient } from '@/utils/supabase/server-internal';
import { createClient as createSessionClient } from '@/utils/supabase/server';

const ALLOWED_SCENARIOS: EvaluatorTestScenario[] = ['oral', 'written_qcm', 'written_libre', 'written_mixed'];
const TEST_SOURCE = 'dashboard_scenario';

const PREFERRED_ORAL_EXAM_ID = '046cb094-275d-4824-811c-3f1afe19ae41';
const PREFERRED_STUDENT_USER_ID = '8e88a51b-4c16-4637-a5e0-3f0a180fb628';
const PREFERRED_ENROLLMENT_ID = 'fae4040c-e9af-47a8-b651-01be5be9df3a';

function scenarioToExamMode(scenario: EvaluatorTestScenario): 'oral' | 'written' {
  return scenario === 'oral' ? 'oral' : 'written';
}

function randomJoinCode() {
  return Math.random().toString(36).slice(2, 10).toUpperCase();
}

function nowIso() {
  return new Date().toISOString();
}

function buildOralConversationHistory() {
  const started = Date.now() - 10 * 60 * 1000;
  return [
    {
      role: 'assistant',
      content: 'Welcome to the oral exam. Explain polymorphism in Java with one practical example.',
      timestamp: new Date(started).toISOString(),
    },
    {
      role: 'user',
      content:
        'Polymorphism lets the same method call behave differently depending on the concrete object type. For example, a List reference can point to an ArrayList or LinkedList and calling add works with each implementation.',
      timestamp: new Date(started + 90 * 1000).toISOString(),
    },
    {
      role: 'assistant',
      content: 'Compare method overloading and overriding and mention one common pitfall.',
      timestamp: new Date(started + 180 * 1000).toISOString(),
    },
    {
      role: 'user',
      content:
        'Overloading is same method name with different parameter signatures in the same class, while overriding redefines inherited behavior in a subclass. A common pitfall is changing only the return type and expecting overload resolution.',
      timestamp: new Date(started + 280 * 1000).toISOString(),
    },
  ];
}

function buildWrittenAnswer(
  examId: string,
  payload: {
    question_order: number;
    question_type: 'qcm' | 'libre';
    question_text: string;
    max_points: number;
    choices?: string[];
    correct_choice?: string;
    reference_answer?: string;
    student_answer: string;
  },
): ExamWrittenAnswer {
  const ts = nowIso();
  return {
    id: crypto.randomUUID(),
    exam_id: examId,
    created_at: ts,
    updated_at: ts,
    question_order: payload.question_order,
    question_type: payload.question_type,
    question_text: payload.question_text,
    max_points: payload.max_points,
    choices: payload.choices,
    correct_choice: payload.correct_choice,
    reference_answer: payload.reference_answer,
    student_answer: payload.student_answer,
    answer: payload.student_answer,
  };
}

function buildScenarioWrittenAnswers(scenario: EvaluatorTestScenario, examId: string): ExamWrittenAnswer[] {
  if (scenario === 'written_qcm') {
    return [
      buildWrittenAnswer(examId, {
        question_order: 1,
        question_type: 'qcm',
        question_text: 'Which Java keyword is used to inherit a class?',
        max_points: 5,
        choices: ['implements', 'extends', 'inherits', 'super'],
        correct_choice: 'extends',
        student_answer: 'extends',
      }),
      buildWrittenAnswer(examId, {
        question_order: 2,
        question_type: 'qcm',
        question_text: 'Which collection maintains insertion order and allows duplicates?',
        max_points: 5,
        choices: ['HashSet', 'TreeSet', 'ArrayList', 'Hashtable'],
        correct_choice: 'ArrayList',
        student_answer: 'HashSet',
      }),
      buildWrittenAnswer(examId, {
        question_order: 3,
        question_type: 'qcm',
        question_text: 'What is the default value of an int field in Java?',
        max_points: 5,
        choices: ['null', '0', '-1', 'undefined'],
        correct_choice: '0',
        student_answer: '0',
      }),
    ];
  }

  if (scenario === 'written_libre') {
    return [
      buildWrittenAnswer(examId, {
        question_order: 1,
        question_type: 'libre',
        question_text: 'Explain the difference between HashMap and TreeMap in Java.',
        max_points: 10,
        reference_answer:
          'HashMap offers average O(1) operations with no key ordering, while TreeMap keeps keys sorted and offers O(log n) operations.',
        student_answer:
          'HashMap is generally faster and unordered, while TreeMap stores keys in sorted order and is slower because it uses a tree structure.',
      }),
      buildWrittenAnswer(examId, {
        question_order: 2,
        question_type: 'libre',
        question_text: 'Describe how exception handling works in Java and why finally is useful.',
        max_points: 10,
        reference_answer:
          'try contains risky code, catch handles exceptions, and finally executes regardless of exceptions, often for cleanup such as closing resources.',
        student_answer:
          'We use try and catch to handle runtime errors. finally executes even when an exception happens, so it is useful for cleaning resources.',
      }),
    ];
  }

  return [
    buildWrittenAnswer(examId, {
      question_order: 1,
      question_type: 'qcm',
      question_text: 'Which interface is used for lambda expressions in Java?',
      max_points: 5,
      choices: ['Serializable', 'Functional Interface', 'Cloneable', 'Iterable'],
      correct_choice: 'Functional Interface',
      student_answer: 'Functional Interface',
    }),
    buildWrittenAnswer(examId, {
      question_order: 2,
      question_type: 'qcm',
      question_text: 'What does JVM stand for?',
      max_points: 5,
      choices: ['Java Variable Method', 'Java Virtual Machine', 'Java Verified Module', 'Joint Virtual Model'],
      correct_choice: 'Java Virtual Machine',
      student_answer: 'Java Variable Method',
    }),
    buildWrittenAnswer(examId, {
      question_order: 3,
      question_type: 'libre',
      question_text: 'Explain the difference between abstraction and encapsulation.',
      max_points: 10,
      reference_answer:
        'Abstraction hides implementation complexity and exposes essential behavior, while encapsulation bundles data and methods and restricts direct access via access modifiers.',
      student_answer:
        'Abstraction focuses on what an object does, while encapsulation focuses on hiding internal state and controlling access.',
    }),
    buildWrittenAnswer(examId, {
      question_order: 4,
      question_type: 'libre',
      question_text: 'Why is immutability useful in concurrent Java applications?',
      max_points: 10,
      reference_answer:
        'Immutable objects cannot change after construction, reducing shared-state bugs and making concurrent code easier to reason about.',
      student_answer:
        'Immutable objects are thread-safe by design because their state does not change, so race conditions are less likely.',
    }),
  ];
}

async function ensureScenarioExam(
  supabase: SupabaseClient,
  options: {
    teacherUserId: string;
    scenario: EvaluatorTestScenario;
  },
): Promise<Exam> {
  const { teacherUserId, scenario } = options;
  const mode = scenarioToExamMode(scenario);

  if (mode === 'oral') {
    const { data: preferredExam } = await supabase
      .from('exams')
      .select('*')
      .eq('id', PREFERRED_ORAL_EXAM_ID)
      .eq('teacher_user_id', teacherUserId)
      .maybeSingle();

    if (preferredExam) {
      return preferredExam;
    }
  }

  const { data: existingExam, error: existingExamError } = await supabase
    .from('exams')
    .select('*')
    .eq('teacher_user_id', teacherUserId)
    .eq('exam_mode', mode)
    .eq('status', 'published')
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();

  if (existingExamError) {
    throw existingExamError;
  }
  if (existingExam) {
    return existingExam;
  }

  const now = nowIso();
  const { data: createdExam, error: createExamError } = await supabase
    .from('exams')
    .insert({
      teacher_user_id: teacherUserId,
      title: mode === 'oral' ? 'Evaluator Test Oral (Auto)' : 'Evaluator Test Written (Auto)',
      subject: 'Java',
      description: 'Auto-generated exam for evaluator scenario testing.',
      instructions: 'Auto-generated by /api/evaluator/test-written.',
      exam_mode: mode,
      status: 'published',
      difficulty_level: 'intermediate',
      duration_minutes: 20,
      question_count: mode === 'oral' ? 1 : 4,
      max_attempts_per_student: 10,
      allow_retakes: true,
      show_results_immediately: true,
      join_code: randomJoinCode(),
      evaluation_config: { test_source: TEST_SOURCE },
      published_at: now,
    })
    .select('*')
    .single();

  if (createExamError || !createdExam) {
    throw createExamError ?? new Error('Failed to create test exam.');
  }

  return createdExam;
}

async function resolveStudentUserId(supabase: SupabaseClient, examId: string): Promise<string> {
  const { data: preferredEnrollment } = await supabase
    .from('exam_enrollments')
    .select('student_user_id')
    .eq('id', PREFERRED_ENROLLMENT_ID)
    .maybeSingle();
  if (preferredEnrollment?.student_user_id) {
    return preferredEnrollment.student_user_id;
  }

  const { data: enrollmentForExam } = await supabase
    .from('exam_enrollments')
    .select('student_user_id')
    .eq('exam_id', examId)
    .in('status', ['joined', 'authorized'])
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();
  if (enrollmentForExam?.student_user_id) {
    return enrollmentForExam.student_user_id;
  }

  const { data: preferredStudent } = await supabase
    .from('profiles')
    .select('user_id')
    .eq('role', 'student')
    .eq('user_id', PREFERRED_STUDENT_USER_ID)
    .maybeSingle();
  if (preferredStudent?.user_id) {
    return preferredStudent.user_id;
  }

  const { data: anyStudent, error: anyStudentError } = await supabase
    .from('profiles')
    .select('user_id')
    .eq('role', 'student')
    .order('created_at', { ascending: true })
    .limit(1)
    .maybeSingle();

  if (anyStudentError) {
    throw anyStudentError;
  }
  if (!anyStudent?.user_id) {
    throw new Error('No student profile found. Please create at least one student profile first.');
  }

  return anyStudent.user_id;
}

async function ensureEnrollment(
  supabase: SupabaseClient,
  options: {
    examId: string;
    studentUserId: string;
  },
): Promise<ExamEnrollment> {
  const { examId, studentUserId } = options;
  const { data: existingEnrollment, error: existingEnrollmentError } = await supabase
    .from('exam_enrollments')
    .select('*')
    .eq('exam_id', examId)
    .eq('student_user_id', studentUserId)
    .limit(1)
    .maybeSingle();

  if (existingEnrollmentError) {
    throw existingEnrollmentError;
  }
  if (existingEnrollment) {
    return existingEnrollment;
  }

  const { data: createdEnrollment, error: createdEnrollmentError } = await supabase
    .from('exam_enrollments')
    .insert({
      exam_id: examId,
      student_user_id: studentUserId,
      status: 'joined',
      joined_at: nowIso(),
    })
    .select('*')
    .single();

  if (createdEnrollmentError || !createdEnrollment) {
    throw createdEnrollmentError ?? new Error('Failed to create enrollment for test student.');
  }

  return createdEnrollment;
}

async function createScenarioAttempt(
  supabase: SupabaseClient,
  options: {
    scenario: EvaluatorTestScenario;
    exam: Exam;
    studentUserId: string;
    enrollmentId: string;
  },
): Promise<ExamAttempt> {
  const { scenario, exam, studentUserId, enrollmentId } = options;
  const { data: previousAttempt, error: previousAttemptError } = await supabase
    .from('exam_attempts')
    .select('attempt_number')
    .eq('exam_id', exam.id)
    .eq('student_user_id', studentUserId)
    .order('attempt_number', { ascending: false })
    .limit(1)
    .maybeSingle();

  if (previousAttemptError) {
    throw previousAttemptError;
  }

  const attemptNumber = (previousAttempt?.attempt_number ?? 0) + 1;
  const submittedAt = new Date();
  const startedAt = new Date(submittedAt.getTime() - 12 * 60 * 1000);

  const isOral = scenario === 'oral';
  const conversationHistory = isOral ? buildOralConversationHistory() : [];
  const writtenAnswers = isOral ? [] : buildScenarioWrittenAnswers(scenario, exam.id);

  const { data: createdAttempt, error: createAttemptError } = await supabase
    .from('exam_attempts')
    .insert({
      exam_id: exam.id,
      student_user_id: studentUserId,
      enrollment_id: enrollmentId,
      attempt_number: attemptNumber,
      status: 'submitted',
      started_at: startedAt.toISOString(),
      ended_at: submittedAt.toISOString(),
      submitted_at: submittedAt.toISOString(),
      duration_seconds: Math.floor((submittedAt.getTime() - startedAt.getTime()) / 1000),
      conversation_history: conversationHistory,
      written_answers: writtenAnswers,
      evaluator_summary: {
        test_source: TEST_SOURCE,
        test_scenario: scenario,
        created_at: nowIso(),
      },
    })
    .select('*')
    .single();

  if (createAttemptError || !createdAttempt) {
    throw createAttemptError ?? new Error('Failed to create test attempt.');
  }

  return createdAttempt;
}

async function selectOrInsertScenarioAttempt(
  supabase: SupabaseClient,
  options: {
    scenario: EvaluatorTestScenario;
    exam: Exam;
    studentUserId: string;
    enrollmentId: string;
  },
): Promise<{ attempt: ExamAttempt; inserted: boolean }> {
  const { scenario, exam, studentUserId, enrollmentId } = options;
  const { data: existingAttempts, error: existingAttemptsError } = await supabase
    .from('exam_attempts')
    .select('*')
    .eq('exam_id', exam.id)
    .eq('student_user_id', studentUserId)
    .contains('evaluator_summary', {
      test_source: TEST_SOURCE,
      test_scenario: scenario,
    })
    .order('created_at', { ascending: false })
    .limit(1);

  if (existingAttemptsError) {
    throw existingAttemptsError;
  }

  const existingAttempt = existingAttempts?.[0] ?? null;
  if (existingAttempt) {
    return { attempt: existingAttempt, inserted: false };
  }

  const attempt = await createScenarioAttempt(supabase, {
    scenario,
    exam,
    studentUserId,
    enrollmentId,
  });
  return { attempt, inserted: true };
}

export async function POST(request: Request) {
  try {
    const payload = (await request.json().catch(() => ({}))) as { scenario?: string };
    const scenario: EvaluatorTestScenario = ALLOWED_SCENARIOS.includes(payload.scenario as EvaluatorTestScenario)
      ? (payload.scenario as EvaluatorTestScenario)
      : 'written_mixed';

    const sessionSupabase = (await createSessionClient()) as SupabaseClient;
    const adminSupabase = (await createAdminClient()) as SupabaseClient;
    const user = await requireAuthenticatedUser(sessionSupabase);
    const context = await getExamContextForUser(adminSupabase, user.id);

    if (!(context.role === 'teacher' || context.role === 'admin')) {
      return NextResponse.json({ error: 'Only teachers can run evaluator test actions.' }, { status: 403 });
    }

    const exam = await ensureScenarioExam(adminSupabase, {
      teacherUserId: user.id,
      scenario,
    });
    const studentUserId = await resolveStudentUserId(adminSupabase, exam.id);
    const enrollment = await ensureEnrollment(adminSupabase, {
      examId: exam.id,
      studentUserId,
    });
    const { attempt, inserted } = await selectOrInsertScenarioAttempt(adminSupabase, {
      scenario,
      exam,
      studentUserId,
      enrollmentId: enrollment.id,
    });

    const evaluatorResponse = await triggerEvaluatorAttempt({
      attemptId: attempt.id,
      examId: exam.id,
      triggeredByUserId: user.id,
    });

    const labels: Record<EvaluatorTestScenario, string> = {
      oral: 'oral exam',
      written_qcm: 'written QCM exam',
      written_libre: 'written libre exam',
      written_mixed: 'written mixed QCM/libre exam',
    };

    return NextResponse.json({
      success: true,
      scenario,
      message: `${inserted ? 'Inserted' : 'Selected'} DB attempt for ${labels[scenario]} and queued evaluation.`,
      triggered: evaluatorResponse.accepted,
      evaluator: evaluatorResponse,
      attempt: {
        id: attempt.id,
        exam_id: attempt.exam_id,
        student_user_id: attempt.student_user_id,
        inserted,
      },
    });
  } catch (error) {
    const resolvedError = resolveExamServiceError(error, 'POST /api/evaluator/test-written');
    return NextResponse.json(resolvedError.body, { status: resolvedError.status });
  }
}
