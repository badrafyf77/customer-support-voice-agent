import type { SupabaseClient, User } from '@supabase/supabase-js';
import type {
  AppProfile,
  AttemptEvaluatorSummary,
  ConversationMessage,
  Exam,
  ExamAttempt,
  ExamCriterionScores,
  ExamEvaluationConfig,
  ExamEnrollment,
  ExamMode,
  ExamRubricCriterion,
  ExamWrittenAnswer,
  UserExamContext,
  UserRole,
} from '@/lib/database.types';
import type {
  CreateExamInput,
  CreateExamRubricCriterionInput,
  ExamPaginationParams,
  FinishExamAttemptInput,
  JoinExamInput,
  StartExamAttemptInput,
} from '../types';

type AppSupabaseClient = SupabaseClient;

const EXAM_MODES = ['oral', 'written'] as const;
const EXAM_STATUSES = ['draft', 'published', 'closed', 'archived'] as const;
const DIFFICULTY_LEVELS = ['beginner', 'intermediate', 'advanced', 'mixed'] as const;
const ATTEMPT_FINAL_STATUSES = ['submitted', 'evaluated', 'cancelled'] as const;

const DEFAULT_ORAL_RUBRIC: CreateExamRubricCriterionInput[] = [
  { key: 'subject_mastery', label: 'Subject Mastery', weight: 40, displayOrder: 1 },
  { key: 'communication', label: 'Communication', weight: 25, displayOrder: 2 },
  { key: 'reasoning', label: 'Reasoning', weight: 20, displayOrder: 3 },
  { key: 'accuracy', label: 'Accuracy', weight: 15, displayOrder: 4 },
];

const DEFAULT_WRITTEN_RUBRIC: CreateExamRubricCriterionInput[] = [
  { key: 'subject_mastery', label: 'Subject Mastery', weight: 45, displayOrder: 1 },
  { key: 'problem_solving', label: 'Problem Solving', weight: 30, displayOrder: 2 },
  { key: 'clarity', label: 'Clarity and Structure', weight: 25, displayOrder: 3 },
];

function isMissingRubricTableError(error: unknown) {
  if (!error || typeof error !== 'object') {
    return false;
  }

  const payload = error as Record<string, unknown>;
  const code = typeof payload.code === 'string' ? payload.code : '';
  const message = typeof payload.message === 'string' ? payload.message : '';
  const details = typeof payload.details === 'string' ? payload.details : '';
  const hint = typeof payload.hint === 'string' ? payload.hint : '';
  const combined = `${message} ${details} ${hint}`.toLowerCase();

  return (
    code === 'PGRST205' ||
    code === '42P01' ||
    (combined.includes('exam_rubric_criteria') &&
      (combined.includes('could not find the table') || combined.includes('does not exist')))
  );
}

function isNonFatalProfileLookupError(error: unknown) {
  if (!error || typeof error !== 'object') {
    return false;
  }

  const payload = error as Record<string, unknown>;
  const code = typeof payload.code === 'string' ? payload.code : '';
  const message = typeof payload.message === 'string' ? payload.message : '';
  const details = typeof payload.details === 'string' ? payload.details : '';
  const hint = typeof payload.hint === 'string' ? payload.hint : '';
  const combined = `${message} ${details} ${hint}`.toLowerCase();

  return (
    code === 'PGRST205' ||
    code === '42P01' ||
    code === '42501' ||
    (combined.includes('profiles') &&
      (combined.includes('could not find the table') ||
        combined.includes('does not exist') ||
        combined.includes('permission denied')))
  );
}

function buildFakeRubricCriteria(
  exam: Pick<Exam, 'id' | 'exam_mode'>,
  source: CreateExamRubricCriterionInput[] = getDefaultRubricForMode(exam.exam_mode),
): ExamRubricCriterion[] {
  const createdAt = new Date().toISOString();

  return source.map((criterion, index) => {
    const criterionKey = criterion.key ?? slugifyCriterionKey(criterion.label);
    return {
      id: `fake-${exam.id}-${criterionKey}`,
      exam_id: exam.id,
      criterion_key: criterionKey,
      criterion_label: criterion.label,
      description: criterion.description ?? null,
      weight: criterion.weight ?? 25,
      score_min: criterion.scoreMin ?? 0,
      score_max: criterion.scoreMax ?? 100,
      display_order: criterion.displayOrder ?? index + 1,
      created_at: createdAt,
      updated_at: createdAt,
    };
  });
}

export class ExamServiceError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'ExamServiceError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function readTrimmedString(record: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string') {
      const trimmedValue = value.trim();
      if (trimmedValue.length > 0) {
        return trimmedValue;
      }
    }
  }

  return undefined;
}

function readBoolean(record: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'boolean') {
      return value;
    }
  }

  return undefined;
}

function readPositiveInteger(record: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'number' && Number.isInteger(value) && value > 0) {
      return value;
    }
  }

  return undefined;
}

function readStringArray(record: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (!Array.isArray(value)) {
      continue;
    }

    const parsedValues = value
      .filter((item) => typeof item === 'string')
      .map((item) => item.trim())
      .filter((item) => item.length > 0);

    return parsedValues;
  }

  return undefined;
}

function readNullableNumber(record: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    if (!(key in record)) {
      continue;
    }

    const value = record[key];
    if (value === null) {
      return null;
    }

    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
  }

  return undefined;
}

function readEnumValue<T extends string>(record: Record<string, unknown>, allowed: readonly T[], ...keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string') {
      const normalizedValue = value.trim().toLowerCase() as T;
      if (allowed.includes(normalizedValue)) {
        return normalizedValue;
      }
    }
  }

  return undefined;
}

function readNullableIsoDate(record: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    if (!(key in record)) {
      continue;
    }

    const value = record[key];

    if (value === null) {
      return null;
    }

    if (typeof value === 'string') {
      const trimmedValue = value.trim();
      if (trimmedValue.length === 0) {
        return null;
      }

      const parsedDate = new Date(trimmedValue);
      if (Number.isNaN(parsedDate.getTime())) {
        throw new ExamServiceError(`${key} must be a valid ISO date`, 400);
      }

      return parsedDate.toISOString();
    }
  }

  return undefined;
}

function slugifyCriterionKey(value: string) {
  const key = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');

  return key || 'criterion';
}

function normalizeConversationHistory(value: unknown): ConversationMessage[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .filter(isRecord)
    .map((item) => {
      const role = readEnumValue(item, ['user', 'assistant', 'system'] as const, 'role') ?? 'user';
      const content = readTrimmedString(item, 'content') ?? '';
      const timestamp = readNullableIsoDate(item, 'timestamp') ?? new Date().toISOString();

      return {
        role,
        content,
        timestamp,
      };
    })
    .filter((item) => item.content.length > 0);
}

function normalizeWrittenAnswers(value: unknown): ExamWrittenAnswer[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter(isRecord).map((item) => {
    const answer = readTrimmedString(item, 'answer', 'student_answer', 'studentAnswer');
    const studentAnswer = readTrimmedString(item, 'student_answer', 'studentAnswer', 'answer');
    const maxPoints = readNullableNumber(item, 'max_points', 'maxPoints');

    return {
      question_id: readTrimmedString(item, 'question_id', 'questionId'),
      question_order: readPositiveInteger(item, 'question_order', 'questionOrder'),
      question_type: readEnumValue(item, ['qcm', 'libre'] as const, 'question_type', 'questionType'),
      question_text: readTrimmedString(item, 'question_text', 'questionText'),
      max_points: typeof maxPoints === 'number' ? maxPoints : undefined,
      choices: readStringArray(item, 'choices'),
      correct_choice: readTrimmedString(item, 'correct_choice', 'correctChoice'),
      reference_answer: readTrimmedString(
        item,
        'reference_answer',
        'referenceAnswer',
        'correct_answer',
        'correctAnswer',
      ),
      student_answer: studentAnswer,
      answer,
    };
  });
}

function normalizeCriterionScores(value: unknown): ExamCriterionScores {
  if (!isRecord(value)) {
    return {};
  }

  return value as ExamCriterionScores;
}

function normalizeEvaluatorSummary(value: unknown): AttemptEvaluatorSummary {
  if (!isRecord(value)) {
    return {};
  }

  return value as AttemptEvaluatorSummary;
}

function normalizeEvaluationConfig(value: unknown): ExamEvaluationConfig {
  if (!isRecord(value)) {
    return {};
  }

  return value as ExamEvaluationConfig;
}

function getDefaultRubricForMode(examMode: ExamMode): CreateExamRubricCriterionInput[] {
  if (examMode === 'written') {
    return DEFAULT_WRITTEN_RUBRIC;
  }

  return DEFAULT_ORAL_RUBRIC;
}

function normalizeRubricCriteria(value: unknown, examMode: ExamMode): CreateExamRubricCriterionInput[] {
  const sourceCriteria = Array.isArray(value) && value.length > 0 ? value : getDefaultRubricForMode(examMode);
  const seenKeys = new Set<string>();

  const normalizedCriteria = sourceCriteria.filter(isRecord).map((item, index) => {
    const label = readTrimmedString(item, 'label');

    if (!label) {
      throw new ExamServiceError(`rubricCriteria[${index}].label is required`, 400);
    }

    const key = slugifyCriterionKey(readTrimmedString(item, 'key') ?? label);
    if (seenKeys.has(key)) {
      throw new ExamServiceError(`Duplicate rubric criterion key: ${key}`, 400);
    }
    seenKeys.add(key);

    const weight = readNullableNumber(item, 'weight') ?? sourceCriteria[index]?.weight ?? 25;
    const scoreMin = readNullableNumber(item, 'scoreMin', 'score_min') ?? 0;
    const scoreMax = readNullableNumber(item, 'scoreMax', 'score_max') ?? 100;
    const displayOrder = readPositiveInteger(item, 'displayOrder', 'display_order') ?? index + 1;

    if (typeof weight !== 'number' || weight <= 0) {
      throw new ExamServiceError(`rubricCriteria[${index}].weight must be greater than 0`, 400);
    }

    if (typeof scoreMin !== 'number' || typeof scoreMax !== 'number' || scoreMax <= scoreMin) {
      throw new ExamServiceError(`rubricCriteria[${index}] has an invalid score range`, 400);
    }

    return {
      key,
      label,
      description: readTrimmedString(item, 'description') ?? null,
      weight,
      scoreMin,
      scoreMax,
      displayOrder,
    };
  });

  if (normalizedCriteria.length === 0) {
    throw new ExamServiceError('At least one rubric criterion is required', 400);
  }

  return normalizedCriteria;
}

function normalizeCreateExamPayload(
  payload: unknown,
): CreateExamInput & { rubricCriteria: CreateExamRubricCriterionInput[] } {
  const record = isRecord(payload) ? payload : {};
  const title = readTrimmedString(record, 'title');
  const subject = readTrimmedString(record, 'subject');

  if (!title) {
    throw new ExamServiceError('title is required', 400);
  }

  if (!subject) {
    throw new ExamServiceError('subject is required', 400);
  }

  const examMode = readEnumValue(record, EXAM_MODES, 'examMode', 'exam_mode') ?? 'oral';
  const status = readEnumValue(record, EXAM_STATUSES, 'status') ?? 'published';
  const difficultyLevel =
    readEnumValue(record, DIFFICULTY_LEVELS, 'difficultyLevel', 'difficulty_level') ?? 'intermediate';
  const durationMinutes = readPositiveInteger(record, 'durationMinutes', 'duration_minutes') ?? 15;
  const questionCount = readPositiveInteger(record, 'questionCount', 'question_count') ?? 5;
  const maxAttemptsPerStudent = readPositiveInteger(record, 'maxAttemptsPerStudent', 'max_attempts_per_student') ?? 1;
  const allowRetakesInput = readBoolean(record, 'allowRetakes', 'allow_retakes');
  const showResultsImmediately = readBoolean(record, 'showResultsImmediately', 'show_results_immediately') ?? true;
  const allowRetakes = allowRetakesInput ?? maxAttemptsPerStudent > 1;
  const startAt = readNullableIsoDate(record, 'startAt', 'start_at') ?? null;
  const endAt = readNullableIsoDate(record, 'endAt', 'end_at') ?? null;

  if (!allowRetakes && maxAttemptsPerStudent > 1) {
    throw new ExamServiceError('allowRetakes must be true when maxAttemptsPerStudent is greater than 1', 400);
  }

  return {
    title,
    subject,
    description: readTrimmedString(record, 'description') ?? null,
    instructions: readTrimmedString(record, 'instructions') ?? null,
    examMode,
    status,
    difficultyLevel,
    durationMinutes,
    questionCount,
    maxAttemptsPerStudent,
    allowRetakes,
    showResultsImmediately,
    startAt,
    endAt,
    evaluationConfig: normalizeEvaluationConfig(record.evaluationConfig ?? record.evaluation_config),
    rubricCriteria: normalizeRubricCriteria(record.rubricCriteria ?? record.rubric_criteria, examMode),
  };
}

function normalizeJoinExamPayload(payload: unknown): JoinExamInput {
  const record = isRecord(payload) ? payload : {};
  const joinCode = readTrimmedString(record, 'joinCode', 'join_code');

  if (!joinCode) {
    throw new ExamServiceError('joinCode is required', 400);
  }

  return {
    joinCode: joinCode.toUpperCase(),
  };
}

function normalizeStartAttemptPayload(payload: unknown): StartExamAttemptInput {
  const record = isRecord(payload) ? payload : {};

  return {
    reuseInProgressAttempt: readBoolean(record, 'reuseInProgressAttempt', 'reuse_in_progress_attempt') ?? true,
  };
}

function normalizeFinishAttemptPayload(payload: unknown): FinishExamAttemptInput {
  const record = isRecord(payload) ? payload : {};
  const status = readEnumValue(record, ATTEMPT_FINAL_STATUSES, 'status');

  return {
    status,
    conversationHistory: normalizeConversationHistory(record.conversationHistory ?? record.conversation_history),
    writtenAnswers: normalizeWrittenAnswers(record.writtenAnswers ?? record.written_answers),
    overallScore: readNullableNumber(record, 'overallScore', 'overall_score'),
    criterionScores: normalizeCriterionScores(record.criterionScores ?? record.criterion_scores),
    feedback: readTrimmedString(record, 'feedback') ?? null,
    evaluatorSummary: normalizeEvaluatorSummary(record.evaluatorSummary ?? record.evaluator_summary),
    durationSeconds: readNullableNumber(record, 'durationSeconds', 'duration_seconds'),
  };
}

function hasEvaluationPayload(input: FinishExamAttemptInput) {
  return (
    input.overallScore !== undefined ||
    Object.keys(input.criterionScores ?? {}).length > 0 ||
    Boolean(input.feedback) ||
    Object.keys(input.evaluatorSummary ?? {}).length > 0
  );
}

function isTeacherRole(role: UserRole) {
  return role === 'teacher' || role === 'admin';
}

function isStudentRole(role: UserRole) {
  return role === 'student';
}

interface WrittenExamQuestionRow {
  id: string;
  question_order: number;
  question_type: 'qcm' | 'libre';
  question_text: string;
  max_points: number;
  choices: string[] | null;
  correct_choice: string | null;
  reference_answer: string | null;
}

interface WrittenAnswerLookup {
  byQuestionId: Map<string, string>;
  byQuestionText: Map<string, string>;
  orderedAnswers: string[];
}

function buildWrittenAnswerLookup(writtenAnswers: ExamWrittenAnswer[]): WrittenAnswerLookup {
  const byQuestionId = new Map<string, string>();
  const byQuestionText = new Map<string, string>();
  const orderedAnswers: string[] = [];

  for (const writtenAnswer of writtenAnswers) {
    const answerText = (writtenAnswer.student_answer ?? writtenAnswer.answer ?? '').trim();
    orderedAnswers.push(answerText);

    const questionId = writtenAnswer.question_id?.trim();
    if (questionId) {
      byQuestionId.set(questionId, answerText);
    }

    const questionText = writtenAnswer.question_text?.trim();
    if (questionText) {
      byQuestionText.set(questionText, answerText);
    }
  }

  return {
    byQuestionId,
    byQuestionText,
    orderedAnswers,
  };
}

function resolveWrittenAnswerForQuestion(question: WrittenExamQuestionRow, lookup: WrittenAnswerLookup) {
  const questionId = question.id.trim();
  if (questionId.length > 0 && lookup.byQuestionId.has(questionId)) {
    return lookup.byQuestionId.get(questionId) ?? '';
  }

  const questionText = question.question_text.trim();
  if (questionText.length > 0 && lookup.byQuestionText.has(questionText)) {
    return lookup.byQuestionText.get(questionText) ?? '';
  }

  const index = Math.max(question.question_order - 1, 0);
  return lookup.orderedAnswers[index] ?? '';
}

function buildValidatedWrittenAnswersForSubmission(
  questions: WrittenExamQuestionRow[],
  rawWrittenAnswers: ExamWrittenAnswer[],
): ExamWrittenAnswer[] {
  if (questions.length === 0) {
    throw new ExamServiceError(
      'This written exam has no generated questions yet. Ask the teacher to generate questions first.',
      400,
    );
  }

  const lookup = buildWrittenAnswerLookup(rawWrittenAnswers);
  const missingQuestionOrders: number[] = [];

  const writtenAnswers = questions.map((question) => {
    const answerText = resolveWrittenAnswerForQuestion(question, lookup).trim();

    if (answerText.length === 0) {
      missingQuestionOrders.push(question.question_order);
    }

    return {
      question_id: question.id,
      question_order: question.question_order,
      question_type: question.question_type,
      question_text: question.question_text,
      max_points: question.max_points,
      choices: question.choices ?? undefined,
      correct_choice: question.correct_choice ?? undefined,
      reference_answer: question.reference_answer ?? undefined,
      student_answer: answerText,
      answer: answerText,
    } satisfies ExamWrittenAnswer;
  });

  if (missingQuestionOrders.length > 0) {
    throw new ExamServiceError(
      `Please answer every question before submitting. Missing question(s): ${missingQuestionOrders.join(', ')}.`,
      400,
    );
  }

  return writtenAnswers;
}

async function loadAppProfile(supabase: AppSupabaseClient, userId: string): Promise<AppProfile | null> {
  const { data: profiles, error } = await supabase.from('profiles').select('*').eq('user_id', userId).limit(1);

  if (error) {
    const e = error as unknown as Record<string, unknown>;
    console.error('Profile lookup error (code=%s, message=%s):', e.code, e.message, error);

    if (isNonFatalProfileLookupError(error)) {
      return null;
    }

    throw new ExamServiceError('Failed to fetch profile', 500);
  }

  return profiles?.[0] ?? null;
}

async function requireAppProfile(supabase: AppSupabaseClient, userId: string): Promise<AppProfile> {
  const profile = await loadAppProfile(supabase, userId);

  if (!profile) {
    throw new ExamServiceError('Please complete your profile before using exams', 400);
  }

  return profile;
}

async function loadExamOrThrow(supabase: AppSupabaseClient, examId: string): Promise<Exam> {
  const { data: exam, error } = await supabase.from('exams').select('*').eq('id', examId).maybeSingle();

  if (error) {
    throw new ExamServiceError('Failed to fetch exam', 500);
  }

  if (!exam) {
    throw new ExamServiceError('Exam not found', 404);
  }

  return exam;
}

async function loadEnrollmentForStudent(
  supabase: AppSupabaseClient,
  examId: string,
  studentUserId: string,
): Promise<ExamEnrollment | null> {
  const { data: enrollment, error } = await supabase
    .from('exam_enrollments')
    .select('*')
    .eq('exam_id', examId)
    .eq('student_user_id', studentUserId)
    .maybeSingle();

  if (error) {
    throw new ExamServiceError('Failed to fetch exam enrollment', 500);
  }

  return enrollment;
}

export async function requireAuthenticatedUser(supabase: AppSupabaseClient): Promise<User> {
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();

  if (error || !user) {
    throw new ExamServiceError('Unauthorized', 401);
  }

  return user;
}

export function parseExamPagination(searchParams: URLSearchParams): Required<ExamPaginationParams> {
  const requestedLimit = Number.parseInt(searchParams.get('limit') || '10', 10);
  const requestedOffset = Number.parseInt(searchParams.get('offset') || '0', 10);

  return {
    limit: Number.isFinite(requestedLimit) && requestedLimit > 0 ? Math.min(requestedLimit, 100) : 10,
    offset: Number.isFinite(requestedOffset) && requestedOffset >= 0 ? requestedOffset : 0,
  };
}

export async function getExamContextForUser(
  supabase: AppSupabaseClient,
  userId: string,
): Promise<{
  context: UserExamContext;
  hasProfile: boolean;
  role: UserRole | null;
  message: string;
}> {
  let profile: AppProfile | null = null;
  try {
    profile = await loadAppProfile(supabase, userId);
  } catch {
    // Profile table may be inaccessible (e.g. RLS without policies); return no-profile context
  }
  const hasProfile = profile !== null;

  return {
    context: {
      user_id: userId,
      profile,
      role: profile?.role ?? null,
      current_exam: null,
    },
    hasProfile,
    role: profile?.role ?? null,
    message: hasProfile
      ? 'Exam context loaded successfully'
      : 'Finish onboarding to create your Veridex profile before using exams',
  };
}

export async function createExamForTeacher(
  supabase: AppSupabaseClient,
  userId: string,
  payload: unknown,
): Promise<{ exam: Exam; criteria: ExamRubricCriterion[] }> {
  const profile = await requireAppProfile(supabase, userId);

  if (!isTeacherRole(profile.role)) {
    throw new ExamServiceError('Only teachers can create exams', 403);
  }

  const examInput = normalizeCreateExamPayload(payload);
  const publishedAt = examInput.status === 'published' ? new Date().toISOString() : null;

  const { data: exam, error: examError } = await supabase
    .from('exams')
    .insert({
      teacher_user_id: userId,
      title: examInput.title,
      subject: examInput.subject,
      description: examInput.description,
      instructions: examInput.instructions,
      exam_mode: examInput.examMode,
      status: examInput.status,
      difficulty_level: examInput.difficultyLevel,
      duration_minutes: examInput.durationMinutes,
      question_count: examInput.questionCount,
      max_attempts_per_student: examInput.maxAttemptsPerStudent,
      allow_retakes: examInput.allowRetakes,
      show_results_immediately: examInput.showResultsImmediately,
      start_at: examInput.startAt,
      end_at: examInput.endAt,
      evaluation_config: examInput.evaluationConfig ?? {},
      published_at: publishedAt,
    })
    .select('*')
    .single();

  if (examError || !exam) {
    throw new ExamServiceError('Failed to create exam', 500);
  }

  const criteriaPayload = examInput.rubricCriteria.map((criterion, index) => ({
    exam_id: exam.id,
    criterion_key: criterion.key ?? slugifyCriterionKey(criterion.label),
    criterion_label: criterion.label,
    description: criterion.description ?? null,
    weight: criterion.weight ?? 25,
    score_min: criterion.scoreMin ?? 0,
    score_max: criterion.scoreMax ?? 100,
    display_order: criterion.displayOrder ?? index + 1,
  }));

  const { data: criteria, error: criteriaError } = await supabase
    .from('exam_rubric_criteria')
    .insert(criteriaPayload)
    .select('*');

  if (criteriaError || !criteria) {
    if (criteriaError && isMissingRubricTableError(criteriaError)) {
      return {
        exam,
        criteria: buildFakeRubricCriteria(exam, examInput.rubricCriteria),
      };
    }

    await supabase.from('exams').delete().eq('id', exam.id);
    throw new ExamServiceError('Failed to create exam rubric criteria', 500);
  }

  const sortedCriteria = [...criteria].sort((a, b) => a.display_order - b.display_order);
  return {
    exam,
    criteria: sortedCriteria,
  };
}

export async function listExamsForUser(supabase: AppSupabaseClient, userId: string, pagination: ExamPaginationParams) {
  const profile = await requireAppProfile(supabase, userId);
  const limit = pagination.limit ?? 10;
  const offset = pagination.offset ?? 0;

  if (isTeacherRole(profile.role)) {
    const {
      data: exams,
      error,
      count,
    } = await supabase
      .from('exams')
      .select('*', { count: 'exact' })
      .eq('teacher_user_id', userId)
      .order('created_at', { ascending: false })
      .range(offset, offset + limit - 1);

    if (error) {
      throw new ExamServiceError('Failed to fetch exams', 500);
    }

    return {
      role: profile.role,
      exams: exams ?? [],
      enrollments: [] as ExamEnrollment[],
      total: count ?? 0,
      limit,
      offset,
    };
  }

  const {
    data: enrollments,
    error: enrollmentsError,
    count,
  } = await supabase
    .from('exam_enrollments')
    .select('*', { count: 'exact' })
    .eq('student_user_id', userId)
    .order('joined_at', { ascending: false })
    .range(offset, offset + limit - 1);

  if (enrollmentsError) {
    throw new ExamServiceError('Failed to fetch exam enrollments', 500);
  }

  const examIds = (enrollments ?? []).map((enrollment) => enrollment.exam_id);

  if (examIds.length === 0) {
    return {
      role: profile.role,
      exams: [] as Exam[],
      enrollments: [] as ExamEnrollment[],
      total: count ?? 0,
      limit,
      offset,
    };
  }

  const { data: exams, error: examsError } = await supabase.from('exams').select('*').in('id', examIds);

  if (examsError) {
    throw new ExamServiceError('Failed to fetch enrolled exams', 500);
  }

  const examsById = new Map((exams ?? []).map((exam) => [exam.id, exam]));
  const orderedExams = examIds.map((examId) => examsById.get(examId)).filter(Boolean) as Exam[];

  return {
    role: profile.role,
    exams: orderedExams,
    enrollments: enrollments ?? [],
    total: count ?? 0,
    limit,
    offset,
  };
}

export async function getExamByIdForUser(supabase: AppSupabaseClient, userId: string, examId: string) {
  const profile = await requireAppProfile(supabase, userId);
  const exam = await loadExamOrThrow(supabase, examId);

  const { data: criteria, error: criteriaError } = await supabase
    .from('exam_rubric_criteria')
    .select('*')
    .eq('exam_id', examId)
    .order('display_order', { ascending: true });

  if (criteriaError && !isMissingRubricTableError(criteriaError)) {
    throw new ExamServiceError('Failed to fetch exam rubric criteria', 500);
  }

  const resolvedCriteria =
    criteria && criteria.length > 0 ? (criteria as ExamRubricCriterion[]) : buildFakeRubricCriteria(exam);
  let enrollment: ExamEnrollment | null = null;
  let attempts: ExamAttempt[] = [];
  let stats: { enrollmentCount: number; attemptCount: number } | null = null;

  if (isStudentRole(profile.role)) {
    enrollment = await loadEnrollmentForStudent(supabase, examId, userId);
    const { data: ownAttempts, error: attemptsError } = await supabase
      .from('exam_attempts')
      .select('*')
      .eq('exam_id', examId)
      .eq('student_user_id', userId)
      .order('attempt_number', { ascending: false });

    if (attemptsError) {
      throw new ExamServiceError('Failed to fetch exam attempts', 500);
    }

    attempts = ownAttempts ?? [];
  } else if (exam.teacher_user_id === userId) {
    const [enrollmentCountResult, attemptCountResult] = await Promise.all([
      supabase.from('exam_enrollments').select('*', { count: 'exact', head: true }).eq('exam_id', examId),
      supabase.from('exam_attempts').select('*', { count: 'exact', head: true }).eq('exam_id', examId),
    ]);

    if (enrollmentCountResult.error || attemptCountResult.error) {
      throw new ExamServiceError('Failed to fetch exam statistics', 500);
    }

    stats = {
      enrollmentCount: enrollmentCountResult.count ?? 0,
      attemptCount: attemptCountResult.count ?? 0,
    };
  }

  return {
    exam,
    criteria: resolvedCriteria,
    enrollment,
    attempts,
    stats,
  };
}

export async function joinExamForStudent(
  supabase: AppSupabaseClient,
  userId: string,
  payload: unknown,
): Promise<{ exam: Exam; enrollment: ExamEnrollment; alreadyJoined: boolean }> {
  const profile = await requireAppProfile(supabase, userId);

  if (!isStudentRole(profile.role)) {
    throw new ExamServiceError('Only students can join exams', 403);
  }

  const input = normalizeJoinExamPayload(payload);
  const { data: exam, error: examError } = await supabase
    .from('exams')
    .select('*')
    .eq('join_code', input.joinCode)
    .maybeSingle();

  if (examError) {
    throw new ExamServiceError('Failed to find exam', 500);
  }

  if (!exam) {
    throw new ExamServiceError('Exam not found for this join code', 404);
  }

  if (exam.status === 'closed' || exam.status === 'archived') {
    throw new ExamServiceError('This exam is closed', 400);
  }

  const existingEnrollment = await loadEnrollmentForStudent(supabase, exam.id, userId);
  if (existingEnrollment) {
    if (existingEnrollment.status === 'revoked') {
      throw new ExamServiceError('Your enrollment has been revoked for this exam', 403);
    }

    return {
      exam,
      enrollment: existingEnrollment,
      alreadyJoined: true,
    };
  }

  const { data: enrollment, error: enrollmentError } = await supabase
    .from('exam_enrollments')
    .insert({
      exam_id: exam.id,
      student_user_id: userId,
      status: 'joined',
    })
    .select('*')
    .single();

  if (enrollmentError || !enrollment) {
    throw new ExamServiceError('Failed to join exam', 500);
  }

  return {
    exam,
    enrollment,
    alreadyJoined: false,
  };
}

export async function startExamAttemptForStudent(
  supabase: AppSupabaseClient,
  userId: string,
  examId: string,
  payload: unknown,
): Promise<{ exam: Exam; attempt: ExamAttempt; reused: boolean }> {
  const profile = await requireAppProfile(supabase, userId);

  if (!isStudentRole(profile.role)) {
    throw new ExamServiceError('Only students can start exam attempts', 403);
  }

  const input = normalizeStartAttemptPayload(payload);
  const exam = await loadExamOrThrow(supabase, examId);

  if (exam.status === 'closed' || exam.status === 'archived') {
    throw new ExamServiceError('This exam is closed', 400);
  }

  const enrollment = await loadEnrollmentForStudent(supabase, examId, userId);
  if (!enrollment || enrollment.status === 'revoked') {
    throw new ExamServiceError('You must join this exam before starting an attempt', 403);
  }

  if (input.reuseInProgressAttempt) {
    const { data: inProgressAttempt, error: inProgressError } = await supabase
      .from('exam_attempts')
      .select('*')
      .eq('exam_id', examId)
      .eq('student_user_id', userId)
      .eq('status', 'in_progress')
      .order('attempt_number', { ascending: false })
      .limit(1)
      .maybeSingle();

    if (inProgressError) {
      throw new ExamServiceError('Failed to fetch in-progress attempt', 500);
    }

    if (inProgressAttempt) {
      return {
        exam,
        attempt: inProgressAttempt,
        reused: true,
      };
    }
  }

  const { data: previousAttempts, error: attemptsError } = await supabase
    .from('exam_attempts')
    .select('attempt_number')
    .eq('exam_id', examId)
    .eq('student_user_id', userId)
    .order('attempt_number', { ascending: false });

  if (attemptsError) {
    throw new ExamServiceError('Failed to determine previous attempts', 500);
  }

  const existingAttempts = previousAttempts ?? [];
  if (existingAttempts.length >= exam.max_attempts_per_student) {
    throw new ExamServiceError('You have already used all allowed attempts for this exam', 400);
  }

  const nextAttemptNumber = (existingAttempts[0]?.attempt_number ?? 0) + 1;

  const { data: attempt, error: attemptError } = await supabase
    .from('exam_attempts')
    .insert({
      exam_id: examId,
      student_user_id: userId,
      enrollment_id: enrollment.id,
      attempt_number: nextAttemptNumber,
      status: 'in_progress',
      started_at: new Date().toISOString(),
    })
    .select('*')
    .single();

  if (attemptError || !attempt) {
    throw new ExamServiceError('Failed to start exam attempt', 500);
  }

  return {
    exam,
    attempt,
    reused: false,
  };
}

export async function getExamAttemptsForUser(
  supabase: AppSupabaseClient,
  userId: string,
  examId: string,
  pagination: ExamPaginationParams,
) {
  const profile = await requireAppProfile(supabase, userId);
  const exam = await loadExamOrThrow(supabase, examId);
  const limit = pagination.limit ?? 10;
  const offset = pagination.offset ?? 0;

  if (exam.teacher_user_id === userId) {
    const {
      data: attempts,
      error,
      count,
    } = await supabase
      .from('exam_attempts')
      .select('*', { count: 'exact' })
      .eq('exam_id', examId)
      .order('created_at', { ascending: false })
      .range(offset, offset + limit - 1);

    if (error) {
      throw new ExamServiceError('Failed to fetch exam attempts', 500);
    }

    const studentIds = Array.from(new Set((attempts ?? []).map((attempt) => attempt.student_user_id)));
    const profilesByUserId: Record<string, AppProfile> = {};

    if (studentIds.length > 0) {
      const { data: profiles, error: profilesError } = await supabase
        .from('profiles')
        .select('*')
        .in('user_id', studentIds);

      if (profilesError) {
        throw new ExamServiceError('Failed to fetch attempt participant profiles', 500);
      }

      for (const appProfile of profiles ?? []) {
        profilesByUserId[appProfile.user_id] = appProfile;
      }
    }

    return {
      exam,
      attempts: attempts ?? [],
      profilesByUserId,
      total: count ?? 0,
      limit,
      offset,
    };
  }

  if (!isStudentRole(profile.role)) {
    throw new ExamServiceError('You are not allowed to view attempts for this exam', 403);
  }

  const {
    data: attempts,
    error,
    count,
  } = await supabase
    .from('exam_attempts')
    .select('*', { count: 'exact' })
    .eq('exam_id', examId)
    .eq('student_user_id', userId)
    .order('attempt_number', { ascending: false })
    .range(offset, offset + limit - 1);

  if (error) {
    throw new ExamServiceError('Failed to fetch your exam attempts', 500);
  }

  return {
    exam,
    attempts: attempts ?? [],
    profilesByUserId: {},
    total: count ?? 0,
    limit,
    offset,
  };
}

export async function finishExamAttemptForUser(
  supabase: AppSupabaseClient,
  userId: string,
  examId: string,
  attemptId: string,
  payload: unknown,
): Promise<ExamAttempt> {
  const profile = await requireAppProfile(supabase, userId);
  const input = normalizeFinishAttemptPayload(payload);
  const exam = await loadExamOrThrow(supabase, examId);

  const { data: attempt, error: attemptError } = await supabase
    .from('exam_attempts')
    .select('*')
    .eq('id', attemptId)
    .eq('exam_id', examId)
    .maybeSingle();

  if (attemptError) {
    throw new ExamServiceError('Failed to fetch exam attempt', 500);
  }

  if (!attempt) {
    throw new ExamServiceError('Exam attempt not found', 404);
  }

  const isTeacherOwner = exam.teacher_user_id === userId;
  const isStudentOwner = attempt.student_user_id === userId && isStudentRole(profile.role);

  if (!isTeacherOwner && !isStudentOwner) {
    throw new ExamServiceError('You are not allowed to finish this exam attempt', 403);
  }

  if (isStudentOwner && hasEvaluationPayload(input)) {
    throw new ExamServiceError('Students cannot write evaluation results directly', 403);
  }

  const endedAt = new Date();
  const startedAt = attempt.started_at ? new Date(attempt.started_at) : endedAt;
  const computedDurationSeconds = Math.max(0, Math.floor((endedAt.getTime() - startedAt.getTime()) / 1000));
  const nextStatus = isTeacherOwner
    ? (input.status ?? (hasEvaluationPayload(input) ? 'evaluated' : 'submitted'))
    : input.status === 'cancelled'
      ? 'cancelled'
      : 'submitted';

  let nextWrittenAnswers =
    input.writtenAnswers && input.writtenAnswers.length > 0 ? input.writtenAnswers : attempt.written_answers;

  const shouldValidateWrittenSubmission = isStudentOwner && exam.exam_mode === 'written' && nextStatus === 'submitted';

  if (shouldValidateWrittenSubmission) {
    const { data: examQuestions, error: examQuestionsError } = await supabase
      .from('exam_questions')
      .select('id, question_order, question_type, question_text, max_points, choices, correct_choice, reference_answer')
      .eq('exam_id', examId)
      .order('question_order', { ascending: true });

    if (examQuestionsError) {
      throw new ExamServiceError('Failed to load written exam questions', 500);
    }

    nextWrittenAnswers = buildValidatedWrittenAnswersForSubmission(
      (examQuestions ?? []) as WrittenExamQuestionRow[],
      nextWrittenAnswers,
    );
  }

  const updatePayload = {
    status: nextStatus,
    ended_at: endedAt.toISOString(),
    submitted_at: nextStatus === 'cancelled' ? attempt.submitted_at : endedAt.toISOString(),
    duration_seconds:
      typeof input.durationSeconds === 'number' && Number.isFinite(input.durationSeconds)
        ? input.durationSeconds
        : computedDurationSeconds,
    conversation_history:
      input.conversationHistory && input.conversationHistory.length > 0
        ? input.conversationHistory
        : attempt.conversation_history,
    written_answers: nextWrittenAnswers,
    overall_score: isTeacherOwner ? (input.overallScore ?? attempt.overall_score) : attempt.overall_score,
    criterion_scores: isTeacherOwner ? (input.criterionScores ?? attempt.criterion_scores) : attempt.criterion_scores,
    feedback: isTeacherOwner ? (input.feedback ?? attempt.feedback) : attempt.feedback,
    evaluator_summary: isTeacherOwner
      ? (input.evaluatorSummary ?? attempt.evaluator_summary)
      : attempt.evaluator_summary,
  };

  const { data: updatedAttempt, error: updateError } = await supabase
    .from('exam_attempts')
    .update(updatePayload)
    .eq('id', attemptId)
    .eq('exam_id', examId)
    .select('*')
    .single();

  if (updateError || !updatedAttempt) {
    throw new ExamServiceError('Failed to finish exam attempt', 500);
  }

  return updatedAttempt;
}

export async function getExamAttemptByIdForUser(
  supabase: AppSupabaseClient,
  userId: string,
  attemptId: string,
): Promise<{ exam: Exam; criteria: ExamRubricCriterion[]; attempt: ExamAttempt }> {
  await requireAppProfile(supabase, userId);

  const { data: attempt, error: attemptError } = await supabase
    .from('exam_attempts')
    .select('*')
    .eq('id', attemptId)
    .maybeSingle();

  if (attemptError) {
    throw new ExamServiceError('Failed to fetch exam attempt', 500);
  }

  if (!attempt) {
    throw new ExamServiceError('Exam attempt not found', 404);
  }

  const exam = await loadExamOrThrow(supabase, attempt.exam_id);
  const { data: criteria, error: criteriaError } = await supabase
    .from('exam_rubric_criteria')
    .select('*')
    .eq('exam_id', exam.id)
    .order('display_order', { ascending: true });

  if (criteriaError && !isMissingRubricTableError(criteriaError)) {
    throw new ExamServiceError('Failed to fetch exam rubric criteria', 500);
  }

  const resolvedCriteria =
    criteria && criteria.length > 0 ? (criteria as ExamRubricCriterion[]) : buildFakeRubricCriteria(exam);

  return {
    exam,
    criteria: resolvedCriteria,
    attempt,
  };
}

export function resolveExamServiceError(error: unknown, context: string) {
  if (error instanceof ExamServiceError) {
    return {
      status: error.status,
      body: {
        error: error.message,
      },
    };
  }

  console.error(`Error in ${context}:`, error);

  return {
    status: 500,
    body: {
      error: 'Internal server error',
    },
  };
}
