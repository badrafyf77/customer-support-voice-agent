import { ExamServiceError } from './exam-service';

const DEFAULT_EVALUATOR_AGENT_BASE_URL = 'http://162.243.59.37:8090';
const EVALUATOR_AGENT_TIMEOUT_MS = 10_000;

interface TriggerEvaluatorAttemptInput {
  attemptId: string;
  examId?: string;
  triggeredByUserId?: string;
}

export interface TriggerEvaluatorAttemptResult {
  accepted: boolean;
  attempt_id: string;
  status: string;
  message?: string;
  result?: Record<string, unknown>;
}

export interface RunSeededEvaluationResult {
  accepted: boolean;
  status: string;
  attempt_id: string;
  message?: string;
  result?: Record<string, unknown>;
}

export type EvaluatorTestScenario = 'oral' | 'written_qcm' | 'written_libre' | 'written_mixed';

interface RequestEvaluatorAgentOptions {
  method?: 'GET' | 'POST' | 'PATCH';
  body?: Record<string, unknown> | undefined;
}

function getEvaluatorAgentBaseUrl() {
  return (process.env.EVALUATOR_AGENT_BASE_URL || DEFAULT_EVALUATOR_AGENT_BASE_URL).replace(/\/+$/, '');
}

async function tryReadErrorMessage(response: Response) {
  try {
    const body = (await response.json()) as { error?: string; message?: string; detail?: string };
    return body.error || body.message || body.detail;
  } catch {
    return undefined;
  }
}

async function requestEvaluatorAgent<T>(path: string, options: RequestEvaluatorAgentOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), EVALUATOR_AGENT_TIMEOUT_MS);

  try {
    const response = await fetch(`${getEvaluatorAgentBaseUrl()}${path}`, {
      method: options.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      cache: 'no-store',
      signal: controller.signal,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });

    if (!response.ok) {
      const serviceMessage = await tryReadErrorMessage(response);
      throw new ExamServiceError(
        serviceMessage || 'Evaluator agent rejected the request',
        response.status >= 500 ? 502 : response.status,
      );
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ExamServiceError) {
      throw error;
    }

    if (error instanceof Error && error.name === 'AbortError') {
      throw new ExamServiceError('Evaluator agent request timed out', 504);
    }

    throw new ExamServiceError('Unable to reach evaluator agent service', 502);
  } finally {
    clearTimeout(timeoutHandle);
  }
}

export async function triggerEvaluatorAttempt({
  attemptId,
  examId,
  triggeredByUserId,
}: TriggerEvaluatorAttemptInput): Promise<TriggerEvaluatorAttemptResult> {
  const trimmedAttemptId = attemptId.trim();
  if (!trimmedAttemptId) {
    throw new ExamServiceError('attemptId is required', 400);
  }

  return requestEvaluatorAgent<TriggerEvaluatorAttemptResult>('/evaluate-attempt', {
    method: 'POST',
    body: {
      attempt_id: trimmedAttemptId,
      exam_id: examId?.trim() || undefined,
      triggered_by_user_id: triggeredByUserId?.trim() || undefined,
      mode: 'async',
    },
  });
}

export async function fetchEvaluationDetail(evaluationId: string) {
  const trimmedEvaluationId = evaluationId.trim();
  if (!trimmedEvaluationId) {
    throw new ExamServiceError('evaluationId is required', 400);
  }

  return requestEvaluatorAgent<Record<string, unknown>>(`/evaluations/${trimmedEvaluationId}`);
}

export async function fetchTeacherEvaluations(teacherUserId: string) {
  const trimmedTeacherUserId = teacherUserId.trim();
  if (!trimmedTeacherUserId) {
    throw new ExamServiceError('teacherUserId is required', 400);
  }

  return requestEvaluatorAgent<{ teacher_user_id: string; evaluations: Record<string, unknown>[] }>(
    `/teachers/${trimmedTeacherUserId}/evaluations`,
  );
}

export async function fetchStudentEvaluations(studentUserId: string) {
  const trimmedStudentUserId = studentUserId.trim();
  if (!trimmedStudentUserId) {
    throw new ExamServiceError('studentUserId is required', 400);
  }

  return requestEvaluatorAgent<{ student_user_id: string; evaluations: Record<string, unknown>[] }>(
    `/students/${trimmedStudentUserId}/evaluations`,
  );
}

export async function adjustEvaluatorQuestion(
  evaluationId: string,
  questionId: string,
  input: { adjusted_score: number; comment?: string | null },
) {
  const trimmedEvaluationId = evaluationId.trim();
  const trimmedQuestionId = questionId.trim();
  if (!trimmedEvaluationId || !trimmedQuestionId) {
    throw new ExamServiceError('evaluationId and questionId are required', 400);
  }

  return requestEvaluatorAgent<Record<string, unknown>>(
    `/evaluations/${trimmedEvaluationId}/questions/${trimmedQuestionId}`,
    {
      method: 'PATCH',
      body: input,
    },
  );
}

export async function createEvaluatorContestation(
  evaluationId: string,
  input: { question_id: string; student_justification: string },
) {
  const trimmedEvaluationId = evaluationId.trim();
  if (!trimmedEvaluationId) {
    throw new ExamServiceError('evaluationId is required', 400);
  }

  return requestEvaluatorAgent<Record<string, unknown>>(`/evaluations/${trimmedEvaluationId}/contest`, {
    method: 'POST',
    body: input,
  });
}

export async function approveEvaluatorReEvalRequest(
  requestId: string,
  input: { teacher_response?: string | null } = {},
) {
  const trimmedRequestId = requestId.trim();
  if (!trimmedRequestId) {
    throw new ExamServiceError('requestId is required', 400);
  }

  return requestEvaluatorAgent<Record<string, unknown>>(`/re-eval-requests/${trimmedRequestId}/approve`, {
    method: 'POST',
    body: input,
  });
}

export async function rejectEvaluatorReEvalRequest(requestId: string, input: { reason: string }) {
  const trimmedRequestId = requestId.trim();
  if (!trimmedRequestId) {
    throw new ExamServiceError('requestId is required', 400);
  }

  return requestEvaluatorAgent<Record<string, unknown>>(`/re-eval-requests/${trimmedRequestId}/reject`, {
    method: 'POST',
    body: input,
  });
}

export async function runSeededEvaluationTest(scenario: EvaluatorTestScenario) {
  return requestEvaluatorAgent<RunSeededEvaluationResult>('/dev/run-seeded-evaluation', {
    method: 'POST',
    body: {
      mode: 'async',
      attempt_kind: scenario,
      force_recompute: true,
    },
  });
}
