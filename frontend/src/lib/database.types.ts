// Shared database types for Veridex.

export type UserRole = 'teacher' | 'student' | 'admin';
export type ExamMode = 'oral' | 'written' | 'hybrid';
export type ExamStatus = 'draft' | 'published' | 'closed' | 'archived';
export type EnrollmentStatus = 'joined' | 'authorized' | 'revoked';
export type ExamAttemptStatus = 'in_progress' | 'submitted' | 'evaluated' | 'cancelled' | 'expired';
export type QuestionType = 'qcm' | 'libre' | 'oral';
export type ReEvalStatus = 'pending' | 'approved' | 'rejected' | 'completed';

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | { [key: string]: JsonValue | undefined } | JsonValue[];

export interface ExamEvaluationConfig {
  passing_score?: number | null;
  rubric_style?: 'fixed' | 'custom';
  randomize_questions?: boolean;
  allow_follow_up_questions?: boolean;
  [key: string]: JsonValue | undefined;
}

export interface ExamCriterionScore {
  score?: number | null;
  feedback?: string | null;
  notes?: string | null;
  [key: string]: JsonValue | undefined;
}

export type ExamCriterionScores = Record<string, ExamCriterionScore>;

export interface ExamWrittenAnswer {
  question_id?: string;
  question_order?: number;
  question_type?: Extract<QuestionType, 'qcm' | 'libre'>;
  question_text?: string;
  max_points?: number;
  choices?: string[];
  correct_choice?: string;
  reference_answer?: string;
  student_answer?: string;
  answer?: string;
  [key: string]: JsonValue | undefined;
}

export interface AttemptEvaluatorSummary {
  strengths?: string[];
  improvements?: string[];
  recommendations?: string[];
  [key: string]: JsonValue | undefined;
}

export interface QuestionCriteriaBreakdownItem {
  name: string;
  score: number;
  max_score: number;
  justification: string;
  [key: string]: JsonValue | undefined;
}

export interface QuestionCriteriaBreakdown {
  criteria_results?: QuestionCriteriaBreakdownItem[];
  [key: string]: JsonValue | undefined;
}

export interface Database {
  public: {
    Tables: {
      profiles: {
        Row: {
          id: string;
          user_id: string;
          role: UserRole;
          full_name: string;
          email: string;
          institution_name: string | null;
          department: string | null;
          academic_level: string | null;
          field_of_study: string | null;
          bio: string | null;
          voice_reference: Record<string, unknown>;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          user_id: string;
          role: UserRole;
          full_name: string;
          email: string;
          institution_name?: string | null;
          department?: string | null;
          academic_level?: string | null;
          field_of_study?: string | null;
          bio?: string | null;
          voice_reference?: Record<string, unknown>;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          user_id?: string;
          role?: UserRole;
          full_name?: string;
          email?: string;
          institution_name?: string | null;
          department?: string | null;
          academic_level?: string | null;
          field_of_study?: string | null;
          bio?: string | null;
          voice_reference?: Record<string, unknown>;
          created_at?: string;
          updated_at?: string;
        };
      };
      exams: {
        Row: {
          id: string;
          teacher_user_id: string;
          title: string;
          subject: string;
          description: string | null;
          instructions: string | null;
          exam_mode: ExamMode;
          status: ExamStatus;
          difficulty_level: 'beginner' | 'intermediate' | 'advanced' | 'mixed';
          duration_minutes: number;
          question_count: number;
          max_attempts_per_student: number;
          allow_retakes: boolean;
          show_results_immediately: boolean;
          start_at: string | null;
          end_at: string | null;
          join_code: string;
          evaluation_config: ExamEvaluationConfig;
          published_at: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          teacher_user_id: string;
          title: string;
          subject: string;
          description?: string | null;
          instructions?: string | null;
          exam_mode?: ExamMode;
          status?: ExamStatus;
          difficulty_level?: 'beginner' | 'intermediate' | 'advanced' | 'mixed';
          duration_minutes?: number;
          question_count?: number;
          max_attempts_per_student?: number;
          allow_retakes?: boolean;
          show_results_immediately?: boolean;
          start_at?: string | null;
          end_at?: string | null;
          join_code?: string;
          evaluation_config?: ExamEvaluationConfig;
          published_at?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          teacher_user_id?: string;
          title?: string;
          subject?: string;
          description?: string | null;
          instructions?: string | null;
          exam_mode?: ExamMode;
          status?: ExamStatus;
          difficulty_level?: 'beginner' | 'intermediate' | 'advanced' | 'mixed';
          duration_minutes?: number;
          question_count?: number;
          max_attempts_per_student?: number;
          allow_retakes?: boolean;
          show_results_immediately?: boolean;
          start_at?: string | null;
          end_at?: string | null;
          join_code?: string;
          evaluation_config?: ExamEvaluationConfig;
          published_at?: string | null;
          created_at?: string;
          updated_at?: string;
        };
      };
      exam_rubric_criteria: {
        Row: {
          id: string;
          exam_id: string;
          criterion_key: string;
          criterion_label: string;
          description: string | null;
          weight: number;
          score_min: number;
          score_max: number;
          display_order: number;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          exam_id: string;
          criterion_key: string;
          criterion_label: string;
          description?: string | null;
          weight?: number;
          score_min?: number;
          score_max?: number;
          display_order?: number;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          exam_id?: string;
          criterion_key?: string;
          criterion_label?: string;
          description?: string | null;
          weight?: number;
          score_min?: number;
          score_max?: number;
          display_order?: number;
          created_at?: string;
          updated_at?: string;
        };
      };
      exam_enrollments: {
        Row: {
          id: string;
          exam_id: string;
          student_user_id: string;
          status: EnrollmentStatus;
          joined_at: string;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          exam_id: string;
          student_user_id: string;
          status?: EnrollmentStatus;
          joined_at?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          exam_id?: string;
          student_user_id?: string;
          status?: EnrollmentStatus;
          joined_at?: string;
          created_at?: string;
          updated_at?: string;
        };
      };
      exam_questions: {
        Row: {
          id: string;
          exam_id: string;
          question_order: number;
          question_type: Extract<QuestionType, 'qcm' | 'libre'>;
          question_text: string;
          max_points: number;
          choices: string[] | null;
          correct_choice: string | null;
          reference_answer: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          exam_id: string;
          question_order: number;
          question_type: Extract<QuestionType, 'qcm' | 'libre'>;
          question_text: string;
          max_points: number;
          choices?: string[] | null;
          correct_choice?: string | null;
          reference_answer?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          exam_id?: string;
          question_order?: number;
          question_type?: Extract<QuestionType, 'qcm' | 'libre'>;
          question_text?: string;
          max_points?: number;
          choices?: string[] | null;
          correct_choice?: string | null;
          reference_answer?: string | null;
          created_at?: string;
          updated_at?: string;
        };
      };
      exam_attempts: {
        Row: {
          id: string;
          exam_id: string;
          student_user_id: string;
          enrollment_id: string | null;
          attempt_number: number;
          status: ExamAttemptStatus;
          started_at: string | null;
          ended_at: string | null;
          submitted_at: string | null;
          duration_seconds: number | null;
          conversation_history: ConversationMessage[];
          written_answers: ExamWrittenAnswer[];
          overall_score: number | null;
          criterion_scores: ExamCriterionScores;
          feedback: string | null;
          evaluator_summary: AttemptEvaluatorSummary;
          voice_reference: Record<string, unknown>;
          voice_verification: Record<string, unknown>;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          exam_id: string;
          student_user_id: string;
          enrollment_id?: string | null;
          attempt_number?: number;
          status?: ExamAttemptStatus;
          started_at?: string | null;
          ended_at?: string | null;
          submitted_at?: string | null;
          duration_seconds?: number | null;
          conversation_history?: ConversationMessage[];
          written_answers?: ExamWrittenAnswer[];
          overall_score?: number | null;
          criterion_scores?: ExamCriterionScores;
          feedback?: string | null;
          evaluator_summary?: AttemptEvaluatorSummary;
          voice_reference?: Record<string, unknown>;
          voice_verification?: Record<string, unknown>;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          exam_id?: string;
          student_user_id?: string;
          enrollment_id?: string | null;
          attempt_number?: number;
          status?: ExamAttemptStatus;
          started_at?: string | null;
          ended_at?: string | null;
          submitted_at?: string | null;
          duration_seconds?: number | null;
          conversation_history?: ConversationMessage[];
          written_answers?: ExamWrittenAnswer[];
          overall_score?: number | null;
          criterion_scores?: ExamCriterionScores;
          feedback?: string | null;
          evaluator_summary?: AttemptEvaluatorSummary;
          voice_reference?: Record<string, unknown>;
          voice_verification?: Record<string, unknown>;
          created_at?: string;
          updated_at?: string;
        };
      };
      exam_question_results: {
        Row: {
          id: string;
          attempt_id: string;
          question_id: string | null;
          question_type: QuestionType;
          question_order: number | null;
          score: number | null;
          max_points: number | null;
          is_correct: boolean | null;
          feedback: string | null;
          student_answer: string | null;
          correct_answer: string | null;
          criteria_breakdown: QuestionCriteriaBreakdown | null;
          teacher_adjusted_score: number | null;
          teacher_comment: string | null;
          re_evaluated: boolean;
          re_eval_score: number | null;
          re_eval_feedback: string | null;
          created_at: string;
        };
        Insert: {
          id?: string;
          attempt_id: string;
          question_id?: string | null;
          question_type: QuestionType;
          question_order?: number | null;
          score?: number | null;
          max_points?: number | null;
          is_correct?: boolean | null;
          feedback?: string | null;
          student_answer?: string | null;
          correct_answer?: string | null;
          criteria_breakdown?: QuestionCriteriaBreakdown | null;
          teacher_adjusted_score?: number | null;
          teacher_comment?: string | null;
          re_evaluated?: boolean;
          re_eval_score?: number | null;
          re_eval_feedback?: string | null;
          created_at?: string;
        };
        Update: {
          id?: string;
          attempt_id?: string;
          question_id?: string | null;
          question_type?: QuestionType;
          question_order?: number | null;
          score?: number | null;
          max_points?: number | null;
          is_correct?: boolean | null;
          feedback?: string | null;
          student_answer?: string | null;
          correct_answer?: string | null;
          criteria_breakdown?: QuestionCriteriaBreakdown | null;
          teacher_adjusted_score?: number | null;
          teacher_comment?: string | null;
          re_evaluated?: boolean;
          re_eval_score?: number | null;
          re_eval_feedback?: string | null;
          created_at?: string;
        };
      };
      re_eval_requests: {
        Row: {
          id: string;
          attempt_id: string;
          question_result_id: string;
          question_id: string | null;
          student_user_id: string;
          student_justification: string;
          status: ReEvalStatus;
          teacher_response: string | null;
          contestation_response: string | null;
          created_at: string;
          resolved_at: string | null;
        };
        Insert: {
          id?: string;
          attempt_id: string;
          question_result_id: string;
          question_id?: string | null;
          student_user_id: string;
          student_justification: string;
          status?: ReEvalStatus;
          teacher_response?: string | null;
          contestation_response?: string | null;
          created_at?: string;
          resolved_at?: string | null;
        };
        Update: {
          id?: string;
          attempt_id?: string;
          question_result_id?: string;
          question_id?: string | null;
          student_user_id?: string;
          student_justification?: string;
          status?: ReEvalStatus;
          teacher_response?: string | null;
          contestation_response?: string | null;
          created_at?: string;
          resolved_at?: string | null;
        };
      };
    };
  };
}

// Conversation message structure
export interface ConversationMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

// Helper types for API responses
export type AppProfile = Database['public']['Tables']['profiles']['Row'];
export type AppProfileInsert = Database['public']['Tables']['profiles']['Insert'];
export type AppProfileUpdate = Database['public']['Tables']['profiles']['Update'];

export type Exam = Database['public']['Tables']['exams']['Row'];
export type ExamInsert = Database['public']['Tables']['exams']['Insert'];
export type ExamUpdate = Database['public']['Tables']['exams']['Update'];

export type ExamRubricCriterion = Database['public']['Tables']['exam_rubric_criteria']['Row'];
export type ExamRubricCriterionInsert = Database['public']['Tables']['exam_rubric_criteria']['Insert'];
export type ExamRubricCriterionUpdate = Database['public']['Tables']['exam_rubric_criteria']['Update'];

export type ExamEnrollment = Database['public']['Tables']['exam_enrollments']['Row'];
export type ExamEnrollmentInsert = Database['public']['Tables']['exam_enrollments']['Insert'];
export type ExamEnrollmentUpdate = Database['public']['Tables']['exam_enrollments']['Update'];

export type ExamQuestion = Database['public']['Tables']['exam_questions']['Row'];
export type ExamQuestionInsert = Database['public']['Tables']['exam_questions']['Insert'];
export type ExamQuestionUpdate = Database['public']['Tables']['exam_questions']['Update'];

export type ExamAttempt = Database['public']['Tables']['exam_attempts']['Row'];
export type ExamAttemptInsert = Database['public']['Tables']['exam_attempts']['Insert'];
export type ExamAttemptUpdate = Database['public']['Tables']['exam_attempts']['Update'];

export type ExamQuestionResult = Database['public']['Tables']['exam_question_results']['Row'];
export type ExamQuestionResultInsert = Database['public']['Tables']['exam_question_results']['Insert'];
export type ExamQuestionResultUpdate = Database['public']['Tables']['exam_question_results']['Update'];

export type ReEvalRequest = Database['public']['Tables']['re_eval_requests']['Row'];
export type ReEvalRequestInsert = Database['public']['Tables']['re_eval_requests']['Insert'];
export type ReEvalRequestUpdate = Database['public']['Tables']['re_eval_requests']['Update'];

export interface UserExamContext {
  user_id: string;
  profile: AppProfile | null;
  role: UserRole | null;
  current_exam: Exam | null;
}
