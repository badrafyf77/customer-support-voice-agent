import type {
  AppProfile,
  AttemptEvaluatorSummary,
  ConversationMessage,
  Exam,
  ExamAttempt,
  ExamCriterionScores,
  ExamWrittenAnswer,
  ExamEnrollment,
  ExamQuestion,
  ExamQuestionResult,
  ExamRubricCriterion,
  ExamEvaluationConfig,
  ExamMode,
  ExamStatus,
  QuestionType,
  ReEvalRequest,
  UserExamContext,
  UserRole,
} from '@/lib/database.types';

export interface CreateExamRubricCriterionInput {
  key?: string;
  label: string;
  description?: string | null;
  weight?: number;
  scoreMin?: number;
  scoreMax?: number;
  displayOrder?: number;
}

export interface CreateExamInput {
  title: string;
  subject: string;
  description?: string | null;
  instructions?: string | null;
  examMode?: ExamMode;
  status?: ExamStatus;
  difficultyLevel?: 'beginner' | 'intermediate' | 'advanced' | 'mixed';
  durationMinutes?: number;
  questionCount?: number;
  maxAttemptsPerStudent?: number;
  allowRetakes?: boolean;
  showResultsImmediately?: boolean;
  startAt?: string | null;
  endAt?: string | null;
  evaluationConfig?: ExamEvaluationConfig;
  rubricCriteria?: CreateExamRubricCriterionInput[];
}

export interface JoinExamInput {
  joinCode: string;
}

export interface StartExamAttemptInput {
  reuseInProgressAttempt?: boolean;
}

export interface FinishExamAttemptInput {
  status?: 'submitted' | 'evaluated' | 'cancelled';
  conversationHistory?: ConversationMessage[];
  writtenAnswers?: ExamWrittenAnswer[];
  overallScore?: number | null;
  criterionScores?: ExamCriterionScores;
  feedback?: string | null;
  evaluatorSummary?: AttemptEvaluatorSummary;
  durationSeconds?: number | null;
}

export interface ExamPaginationParams {
  limit?: number;
  offset?: number;
}

export interface ExamRouteError {
  error: string;
}

export interface ExamContextResponse {
  context: UserExamContext;
  hasProfile: boolean;
  role: UserRole | null;
  message: string;
}

export interface CreateExamResponse {
  success: boolean;
  exam: Exam;
  criteria: ExamRubricCriterion[];
  message: string;
}

export interface ExamsListResponse {
  role: UserRole;
  exams: Exam[];
  enrollments: ExamEnrollment[];
  total: number;
  limit: number;
  offset: number;
}

export interface ExamDetailResponse {
  exam: Exam;
  criteria: ExamRubricCriterion[];
  enrollment: ExamEnrollment | null;
  attempts: ExamAttempt[];
  stats: {
    enrollmentCount: number;
    attemptCount: number;
  } | null;
}

export interface JoinExamResponse {
  success: boolean;
  exam: Exam;
  enrollment: ExamEnrollment;
  alreadyJoined: boolean;
  message: string;
}

export interface StartExamAttemptResponse {
  success: boolean;
  exam: Exam;
  attempt: ExamAttempt;
  reused: boolean;
  message: string;
}

export interface FinishExamAttemptResponse {
  success: boolean;
  attempt: ExamAttempt;
  message: string;
  evaluationTriggered?: boolean;
  evaluationTriggerError?: string | null;
  evaluator?: {
    accepted: boolean;
    attempt_id: string;
    status: string;
    message?: string;
  } | null;
}

export interface TriggerAttemptEvaluationInput {
  examId?: string;
}

export interface TriggerAttemptEvaluationResponse {
  success: boolean;
  message: string;
  triggered: boolean;
  evaluator: {
    accepted: boolean;
    attempt_id: string;
    status: string;
    message?: string;
  };
}

export type EvaluatorTestScenario = 'oral' | 'written_qcm' | 'written_libre' | 'written_mixed';

export interface TestEvaluatorAgentResponse {
  success: boolean;
  scenario: EvaluatorTestScenario;
  message: string;
  triggered: boolean;
  evaluator: {
    accepted: boolean;
    attempt_id: string;
    status: string;
    message?: string;
  };
}

export interface ExamAttemptsResponse {
  exam: Exam;
  attempts: ExamAttempt[];
  profilesByUserId: Record<string, AppProfile>;
  total: number;
  limit: number;
  offset: number;
}

export type EvaluationQuestionResultSource = 'original' | 'teacher_adjusted' | 're_evaluated';

export interface EvaluationScoreSummary {
  total_score: number;
  max_total_score: number;
  percentage: number;
}

export interface EvaluationQuestionResult extends ExamQuestionResult {
  effective_score: number;
  effective_feedback: string;
  effective_source: EvaluationQuestionResultSource;
}

export interface EvaluationListItem {
  evaluation_id: string;
  exam_id: string;
  exam_title: string;
  exam_mode: ExamMode;
  student_user_id: string;
  student_name: string | null;
  teacher_user_id: string;
  teacher_name: string | null;
  status: string;
  overall_score: number | null;
  score_summary: EvaluationScoreSummary;
  submitted_at: string | null;
  updated_at: string;
  question_results_count: number;
  pending_contestations: number;
}

export interface EvaluationsResponse {
  role: UserRole | null;
  evaluations: EvaluationListItem[];
}

export interface ExamAttemptResponse {
  exam: Exam;
  criteria: ExamRubricCriterion[];
  attempt: ExamAttempt;
  questions?: ExamQuestion[];
  questionResults?: EvaluationQuestionResult[];
  reEvalRequests?: ReEvalRequest[];
  studentProfile?: AppProfile | null;
  teacherProfile?: AppProfile | null;
  scoreSummary?: EvaluationScoreSummary;
}

export interface ManualQuestionAdjustmentInput {
  adjustedScore: number;
  comment?: string | null;
}

export interface ManualQuestionAdjustmentResponse {
  success: boolean;
  evaluationId: string;
  questionResult: EvaluationQuestionResult;
  attempt: ExamAttempt;
  scoreSummary: EvaluationScoreSummary;
  message: string;
}

export interface CreateContestationInput {
  questionId: string;
  studentJustification: string;
}

export interface CreateContestationResponse {
  success: boolean;
  evaluationId: string;
  reEvalRequest: ReEvalRequest;
  notificationSent?: boolean;
  publishStatus?: string;
  message: string;
}

export interface ApproveReEvalInput {
  teacherResponse?: string | null;
}

export interface RejectReEvalInput {
  reason: string;
}

export interface ReEvalActionResponse {
  success: boolean;
  evaluationId?: string;
  reEvalRequest: ReEvalRequest;
  questionResult?: EvaluationQuestionResult;
  attempt?: ExamAttempt;
  scoreSummary?: EvaluationScoreSummary;
  message: string;
}

export type ExamTranscriptMessageState = 'partial' | 'final';

export interface ExamTranscriptMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  type: ExamTranscriptMessageState;
  timestamp: number;
  finishComplete?: boolean;
  success?: boolean;
  attemptId?: string;
  examId?: string;
  overallScore?: number;
  error?: string;
}

export interface ExamWebSocketMessage {
  type: string;
  content?: string;
  sentence_id?: number;
  speed?: number;
  status?: string;
  message?: string;
  success?: boolean;
  attempt_id?: string;
  exam_id?: string;
  overall_score?: number;
  error?: string;
}

export type {
  AppProfile,
  ConversationMessage,
  Exam,
  ExamAttempt,
  ExamCriterionScores,
  ExamEnrollment,
  ExamEvaluationConfig,
  ExamMode,
  ExamQuestion,
  ExamQuestionResult,
  ExamRubricCriterion,
  ExamStatus,
  ExamWrittenAnswer,
  QuestionType,
  ReEvalRequest,
  UserExamContext,
  UserRole,
};
