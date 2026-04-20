import type {
  ApproveReEvalInput,
  CreateContestationInput,
  CreateContestationResponse,
  CreateExamInput,
  CreateExamResponse,
  ExamAttemptResponse,
  ExamAttemptsResponse,
  ExamContextResponse,
  ExamDetailResponse,
  ExamsListResponse,
  EvaluationsResponse,
  ExamPaginationParams,
  ExamRouteError,
  FinishExamAttemptInput,
  FinishExamAttemptResponse,
  JoinExamInput,
  JoinExamResponse,
  ManualQuestionAdjustmentInput,
  ManualQuestionAdjustmentResponse,
  EvaluatorTestScenario,
  RejectReEvalInput,
  ReEvalActionResponse,
  StartExamAttemptInput,
  StartExamAttemptResponse,
  TestEvaluatorAgentResponse,
  TriggerAttemptEvaluationInput,
  TriggerAttemptEvaluationResponse,
} from '../types';
import { ATTEMPT_EVALUATION_TRIGGER_MAX_ATTEMPTS, ATTEMPT_EVALUATION_TRIGGER_RETRY_DELAY_MS } from '../constants';

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as T | ExamRouteError;

  if (!response.ok) {
    const routeError = payload as ExamRouteError;
    throw new Error(routeError.error || 'Unable to complete the request.');
  }

  return payload as T;
}

function buildQueryString(pagination: ExamPaginationParams = {}) {
  const params = new URLSearchParams();

  if (pagination.limit != null) {
    params.set('limit', pagination.limit.toString());
  }

  if (pagination.offset != null) {
    params.set('offset', pagination.offset.toString());
  }

  const queryString = params.toString();
  return queryString ? `?${queryString}` : '';
}

export async function fetchExamContext(): Promise<ExamContextResponse> {
  return parseResponse<ExamContextResponse>(await fetch('/api/exams/context'));
}

export async function fetchExams(pagination: ExamPaginationParams = {}): Promise<ExamsListResponse> {
  return parseResponse<ExamsListResponse>(await fetch(`/api/exams${buildQueryString(pagination)}`));
}

export async function createExam(input: CreateExamInput): Promise<CreateExamResponse> {
  return parseResponse<CreateExamResponse>(
    await fetch('/api/exams', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(input),
    }),
  );
}

export async function joinExam(input: JoinExamInput): Promise<JoinExamResponse> {
  return parseResponse<JoinExamResponse>(
    await fetch('/api/exams/join', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(input),
    }),
  );
}

export async function fetchExamDetail(examId: string): Promise<ExamDetailResponse> {
  return parseResponse<ExamDetailResponse>(await fetch(`/api/exams/${examId}`));
}

export async function fetchExamAttempts(
  examId: string,
  pagination: ExamPaginationParams = {},
): Promise<ExamAttemptsResponse> {
  return parseResponse<ExamAttemptsResponse>(
    await fetch(`/api/exams/${examId}/attempts${buildQueryString(pagination)}`),
  );
}

export async function startExamAttempt(
  examId: string,
  input: StartExamAttemptInput = {},
): Promise<StartExamAttemptResponse> {
  return parseResponse<StartExamAttemptResponse>(
    await fetch(`/api/exams/${examId}/attempts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(input),
    }),
  );
}

export async function finishExamAttempt(
  examId: string,
  attemptId: string,
  input: FinishExamAttemptInput,
): Promise<FinishExamAttemptResponse> {
  return parseResponse<FinishExamAttemptResponse>(
    await fetch(`/api/exams/${examId}/attempts/${attemptId}/finish`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(input),
    }),
  );
}

export async function fetchExamAttempt(attemptId: string): Promise<ExamAttemptResponse> {
  return parseResponse<ExamAttemptResponse>(await fetch(`/api/attempts/${attemptId}`));
}

export async function fetchEvaluations(): Promise<EvaluationsResponse> {
  return parseResponse<EvaluationsResponse>(await fetch('/api/evaluations'));
}

export async function triggerAttemptEvaluation(
  attemptId: string,
  input: TriggerAttemptEvaluationInput = {},
): Promise<TriggerAttemptEvaluationResponse> {
  return parseResponse<TriggerAttemptEvaluationResponse>(
    await fetch(`/api/attempts/${attemptId}/evaluate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(input),
    }),
  );
}

function waitForEvaluationRetry(delayMs: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, delayMs);
  });
}

interface QueueAttemptEvaluationOptions extends TriggerAttemptEvaluationInput {
  maxAttempts?: number;
  retryDelayMs?: number;
}

export async function queueAttemptEvaluation(
  attemptId: string,
  input: QueueAttemptEvaluationOptions = {},
): Promise<TriggerAttemptEvaluationResponse> {
  const maxAttempts = Math.max(1, input.maxAttempts ?? ATTEMPT_EVALUATION_TRIGGER_MAX_ATTEMPTS);
  const retryDelayMs = Math.max(0, input.retryDelayMs ?? ATTEMPT_EVALUATION_TRIGGER_RETRY_DELAY_MS);
  let lastError: Error | null = null;

  for (let attemptNumber = 1; attemptNumber <= maxAttempts; attemptNumber += 1) {
    try {
      const response = await triggerAttemptEvaluation(attemptId, {
        examId: input.examId,
      });

      if (response.triggered) {
        return response;
      }

      lastError = new Error(
        response.evaluator.message || response.message || 'The evaluator service did not accept the trigger request.',
      );
    } catch (error) {
      lastError = error instanceof Error ? error : new Error('Unable to reach the evaluator service.');
    }

    if (attemptNumber < maxAttempts) {
      await waitForEvaluationRetry(retryDelayMs);
    }
  }

  const reason = lastError?.message || 'The evaluator service did not accept the trigger request.';
  throw new Error(
    `The exam was submitted, but the evaluator could not be queued automatically after ${maxAttempts} attempt${maxAttempts === 1 ? '' : 's'}. ${reason}`,
  );
}

export async function adjustAttemptQuestion(
  attemptId: string,
  questionId: string,
  input: ManualQuestionAdjustmentInput,
): Promise<ManualQuestionAdjustmentResponse> {
  return parseResponse<ManualQuestionAdjustmentResponse>(
    await fetch(`/api/attempts/${attemptId}/questions/${questionId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(input),
    }),
  );
}

export async function createAttemptContestation(
  attemptId: string,
  input: CreateContestationInput,
): Promise<CreateContestationResponse> {
  return parseResponse<CreateContestationResponse>(
    await fetch(`/api/attempts/${attemptId}/contest`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(input),
    }),
  );
}

export async function approveReEvalRequest(
  requestId: string,
  input: ApproveReEvalInput = {},
): Promise<ReEvalActionResponse> {
  return parseResponse<ReEvalActionResponse>(
    await fetch(`/api/re-eval-requests/${requestId}/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(input),
    }),
  );
}

export async function rejectReEvalRequest(requestId: string, input: RejectReEvalInput): Promise<ReEvalActionResponse> {
  return parseResponse<ReEvalActionResponse>(
    await fetch(`/api/re-eval-requests/${requestId}/reject`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(input),
    }),
  );
}

export async function runEvaluatorMockTest(scenario: EvaluatorTestScenario): Promise<TestEvaluatorAgentResponse> {
  return parseResponse<TestEvaluatorAgentResponse>(
    await fetch('/api/evaluator/test-written', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ scenario }),
    }),
  );
}
