'use client';

import Link from 'next/link';
import { type ReactNode, useEffect, useState } from 'react';
import {
  AlertCircle,
  BookOpen,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Loader2,
  ClipboardCheck,
  Clock3,
  ExternalLink,
  FileText,
  GraduationCap,
  Mic,
  PlusCircle,
  RefreshCcw,
  Sparkles,
  RotateCcw,
  Upload,
  Users,
} from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { createExam, fetchExamContext, fetchExams, joinExam } from '../lib/client';
import {
  formatDateTime,
  formatDurationMinutes,
  getExamModeLabel,
  getExamStatusBadgeVariant,
  getRoleLabel,
  isExamOpen,
} from '../lib/formatters';
import type { CreateExamInput, Exam, ExamsListResponse, UserRole } from '../types';

function isTeacherRole(role: UserRole | null) {
  return role === 'teacher' || role === 'admin';
}

type ApiErrorPayload = {
  error?: string;
  message?: string;
  detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>;
};

function getApiErrorMessage(payload: ApiErrorPayload, fallback: string) {
  if (typeof payload.error === 'string' && payload.error.trim()) {
    return payload.error;
  }

  if (typeof payload.message === 'string' && payload.message.trim()) {
    return payload.message;
  }

  if (typeof payload.detail === 'string' && payload.detail.trim()) {
    return payload.detail;
  }

  if (Array.isArray(payload.detail)) {
    const issues = payload.detail
      .map((issue) => {
        const message = typeof issue?.msg === 'string' ? issue.msg : null;
        const location = Array.isArray(issue?.loc) ? issue.loc.join('.') : '';

        if (!message) {
          return null;
        }

        return location ? `${location}: ${message}` : message;
      })
      .filter((issue): issue is string => Boolean(issue));

    if (issues.length > 0) {
      return issues.join('; ');
    }
  }

  return fallback;
}

interface ExamSummaryCardProps {
  label: string;
  value: string | number;
  icon: ReactNode;
  hint: string;
}

function ExamSummaryCard({ label, value, icon, hint }: ExamSummaryCardProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardDescription>{label}</CardDescription>
        <div className="flex items-center justify-between gap-4">
          <CardTitle className="text-3xl">{value}</CardTitle>
          <div className="rounded-full border border-border bg-muted/40 p-3">{icon}</div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <p className="text-sm text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

interface TeacherCreateExamFormProps {
  onCreated: () => Promise<void>;
}

function TeacherCreateExamForm({ onCreated }: TeacherCreateExamFormProps) {
  // ── Exam creation state ──────────────────────────────────────────────────────
  const [title, setTitle] = useState('');
  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [examMode, setExamMode] = useState<CreateExamInput['examMode']>('oral');
  const [difficultyLevel, setDifficultyLevel] = useState<CreateExamInput['difficultyLevel']>('intermediate');
  const [durationMinutes, setDurationMinutes] = useState('15');
  const [questionCount, setQuestionCount] = useState('5');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [createdExam, setCreatedExam] = useState<Exam | null>(null);

  // ── AI generation state ──────────────────────────────────────────────────────
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ doc_id: string; chunks_indexed: number } | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiQuestionType, setAiQuestionType] = useState<'mcq' | 'open' | 'mixed'>('mixed');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  // progressStep: 0 = retrieving, 1 = per-question generation, 2 = validating
  const [progressStep, setProgressStep] = useState(0);
  const [generatingQuestionIndex, setGeneratingQuestionIndex] = useState(0);

  useEffect(() => {
    if (!isGenerating) return;
    const n = createdExam?.question_count ?? 5;
    setProgressStep(0);
    setGeneratingQuestionIndex(0);

    // After 2 s switch to per-question phase
    const t0 = setTimeout(() => setProgressStep(1), 2000);

    // Tick one question every 1.5 s
    const questionTimers = Array.from({ length: n }, (_, i) =>
      setTimeout(() => setGeneratingQuestionIndex(i), 2000 + i * 1500),
    );

    // Validating phase starts after all questions have been "shown"
    const t1 = setTimeout(() => setProgressStep(2), 2000 + n * 1500);

    return () => {
      clearTimeout(t0);
      clearTimeout(t1);
      questionTimers.forEach(clearTimeout);
    };
  }, [isGenerating, createdExam?.question_count]);

  // ── HITL review state ────────────────────────────────────────────────────────
  interface ReviewQuestion {
    type: 'mcq' | 'open';
    question: string;
    answer: string;
    options: string[];
    correct_option_index: number;
  }
  const [reviewQuestions, setReviewQuestions] = useState<ReviewQuestion[] | null>(null);
  const [reviewPage, setReviewPage] = useState(0);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedCount, setSavedCount] = useState<number | null>(null);

  const resetForm = () => {
    setTitle('');
    setSubject('');
    setDescription('');
    setInstructions('');
    setExamMode('oral');
    setDifficultyLevel('intermediate');
    setDurationMinutes('15');
    setQuestionCount('5');
  };

  const handleSubmit = async () => {
    if (!title.trim() || !subject.trim()) {
      setErrorMessage('Title and subject are required.');
      return;
    }
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const response = await createExam({
        title: title.trim(),
        subject: subject.trim(),
        description: description.trim() || null,
        instructions: instructions.trim() || null,
        examMode,
        status: 'published',
        difficultyLevel,
        durationMinutes: Number.parseInt(durationMinutes, 10) || 15,
        questionCount: Number.parseInt(questionCount, 10) || 5,
        maxAttemptsPerStudent: 1,
        allowRetakes: false,
        showResultsImmediately: true,
        startAt: null,
        endAt: null,
      });
      setCreatedExam(response.exam);
      resetForm();
      await onCreated();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to create the exam.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUpload = async () => {
    if (!uploadFile || !createdExam) return;
    setIsUploading(true);
    setAiError(null);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('course_id', createdExam.id);
      const res = await fetch(`/api/exams/${createdExam.id}/upload`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as ApiErrorPayload;
        throw new Error(getApiErrorMessage(data, 'Upload failed.'));
      }
      const data = (await res.json()) as { doc_id: string; chunks_indexed: number };
      setUploadResult(data);
    } catch (error) {
      setAiError(error instanceof Error ? error.message : 'Upload failed.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleGenerate = async () => {
    if (!createdExam || !uploadResult) return;
    setIsGenerating(true);
    setAiError(null);
    try {
      const safeK = Math.min(5, uploadResult.chunks_indexed);

      const res = await fetch(`/api/exams/${createdExam.id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: createdExam.subject,
          n_questions: createdExam.question_count,
          question_type: aiQuestionType,
          course_id: createdExam.id,
          k: safeK,
          max_points: 1.0,
        }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as ApiErrorPayload;
        throw new Error(getApiErrorMessage(data, 'Generation failed.'));
      }
      const data = (await res.json()) as { questions: ReviewQuestion[] };
      setReviewPage(0);
      setReviewQuestions(data.questions);
    } catch (error) {
      setAiError(error instanceof Error ? error.message : 'Generation failed.');
    } finally {
      setIsGenerating(false);
    }
  };

  const updateQuestion = (i: number, field: keyof ReviewQuestion, value: string) => {
    setReviewQuestions((prev) => (prev ? prev.map((q, idx) => (idx === i ? { ...q, [field]: value } : q)) : prev));
  };

  const updateOption = (qi: number, oi: number, value: string) => {
    setReviewQuestions((prev) =>
      prev
        ? prev.map((q, idx) => {
            if (idx !== qi) return q;
            const options = [...q.options];
            options[oi] = value;
            return { ...q, options };
          })
        : prev,
    );
  };

  const setCorrectOption = (qi: number, oi: number) => {
    setReviewQuestions((prev) =>
      prev ? prev.map((q, idx) => (idx === qi ? { ...q, correct_option_index: oi } : q)) : prev,
    );
  };

  const handleRegenerateQuestion = async (qi: number) => {
    if (!createdExam || !uploadResult) return;
    setIsRegenerating(true);
    setSaveError(null);
    try {
      const safeK = Math.min(5, uploadResult.chunks_indexed);
      const res = await fetch(`/api/exams/${createdExam.id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: createdExam.subject,
          n_questions: 1,
          question_type: reviewQuestions?.[qi]?.type ?? aiQuestionType,
          course_id: createdExam.id,
          k: safeK,
          max_points: 1.0,
        }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as ApiErrorPayload;
        throw new Error(getApiErrorMessage(data, 'Regeneration failed.'));
      }
      const data = (await res.json()) as { questions: ReviewQuestion[] };
      if (data.questions.length > 0) {
        setReviewQuestions((prev) => (prev ? prev.map((q, idx) => (idx === qi ? data.questions[0] : q)) : prev));
      }
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Regeneration failed.');
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleSave = async () => {
    if (!createdExam || !reviewQuestions) return;
    setIsSaving(true);
    setSaveError(null);
    try {
      const res = await fetch(`/api/exams/${createdExam.id}/save-questions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          questions: reviewQuestions,
          max_points: 1.0,
        }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as ApiErrorPayload;
        throw new Error(getApiErrorMessage(data, 'Save failed.'));
      }
      const data = (await res.json()) as { saved: number };
      setSavedCount(data.saved);
      setReviewQuestions(null);
      await onCreated();
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Save failed.');
    } finally {
      setIsSaving(false);
    }
  };

  // ── Phase 2: AI generation (shown after exam is created) ─────────────────────
  if (createdExam) {
    const total = reviewQuestions?.length ?? 0;
    const currentQ = reviewQuestions?.[reviewPage] ?? null;

    return (
      <div className="space-y-4">
        {/* ── HITL review dialog ─────────────────────────────────────────────── */}
        <Dialog open={isGenerating || reviewQuestions !== null}>
          <DialogContent className="max-w-lg overflow-hidden" onInteractOutside={(e) => e.preventDefault()}>
            <DialogHeader>
              <div className="flex items-center justify-between gap-3 pr-6">
                <div className="min-w-0">
                  <DialogTitle>{isGenerating ? 'Generating Questions' : 'Review AI Questions'}</DialogTitle>
                  <DialogDescription>
                    {isGenerating
                      ? 'Veridex is building your questions. This may take up to a minute.'
                      : 'Edit or regenerate each question before saving to the exam.'}
                  </DialogDescription>
                </div>
                {!isGenerating ? (
                  <Badge variant="secondary" className="shrink-0">
                    {total} question{total === 1 ? '' : 's'}
                  </Badge>
                ) : null}
              </div>
            </DialogHeader>

            {/* ── Progress steps (shown while generating) ──────────────────── */}
            {isGenerating
              ? (() => {
                  const n = createdExam?.question_count ?? 5;
                  const doneCount = progressStep < 1 ? 0 : Math.min(generatingQuestionIndex, n);
                  const pct = Math.round((doneCount / n) * 100);

                  type RowStatus = 'done' | 'current' | 'pending';
                  const Row = ({ status, label }: { status: RowStatus; label: string }) => (
                    <div
                      className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm ${status === 'current' ? 'bg-muted/60' : ''}`}
                    >
                      {status === 'done' ? (
                        <CheckCircle className="h-4 w-4 shrink-0 text-primary" />
                      ) : status === 'current' ? (
                        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
                      ) : (
                        <div className="h-4 w-4 shrink-0 rounded-full border-2 border-muted-foreground/20" />
                      )}
                      <span
                        className={
                          status === 'done'
                            ? 'text-muted-foreground'
                            : status === 'current'
                              ? 'font-medium'
                              : 'text-muted-foreground/45'
                        }
                      >
                        {label}
                      </span>
                    </div>
                  );

                  return (
                    <div className="py-2 space-y-1">
                      <Row status={progressStep > 0 ? 'done' : 'current'} label="Retrieving course material" />

                      {/* Single compact question progress row */}
                      <div
                        className={`rounded-lg px-3 py-3 text-sm space-y-2 ${progressStep === 1 ? 'bg-muted/60' : ''}`}
                      >
                        <div className="flex items-center gap-3">
                          {progressStep < 1 ? (
                            <div className="h-4 w-4 shrink-0 rounded-full border-2 border-muted-foreground/20" />
                          ) : progressStep === 1 ? (
                            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
                          ) : (
                            <CheckCircle className="h-4 w-4 shrink-0 text-primary" />
                          )}
                          <span
                            className={
                              progressStep < 1
                                ? 'text-muted-foreground/45'
                                : progressStep === 1
                                  ? 'font-medium'
                                  : 'text-muted-foreground'
                            }
                          >
                            {progressStep < 1
                              ? 'Generating questions'
                              : progressStep === 1
                                ? `Generating question ${doneCount + 1} / ${n}…`
                                : `${n} question${n === 1 ? '' : 's'} generated`}
                          </span>
                          {progressStep >= 1 ? (
                            <span className="ml-auto tabular-nums text-xs text-muted-foreground">{pct}%</span>
                          ) : null}
                        </div>

                        {/* Progress bar — only visible during generation phase */}
                        {progressStep >= 1 ? (
                          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                            <div
                              className="h-full rounded-full bg-primary transition-all duration-700 ease-out"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        ) : null}
                      </div>

                      <Row status={progressStep < 2 ? 'pending' : 'current'} label="Validating output" />
                    </div>
                  );
                })()
              : null}

            {/* Question meta bar */}
            {!isGenerating && currentQ ? (
              <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2 text-sm">
                <div className="flex items-center gap-2">
                  <Badge variant={currentQ.type === 'mcq' ? 'default' : 'outline'}>
                    {currentQ.type === 'mcq' ? 'MCQ' : 'Open'}
                  </Badge>
                  <span className="font-medium">
                    Question {reviewPage + 1}
                    <span className="font-normal text-muted-foreground"> / {total}</span>
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  disabled={isRegenerating}
                  onClick={() => handleRegenerateQuestion(reviewPage)}
                  title="Regenerate this question"
                >
                  <RotateCcw className={`h-3.5 w-3.5 ${isRegenerating ? 'animate-spin' : ''}`} />
                </Button>
              </div>
            ) : null}

            {/* Empty state */}
            {!isGenerating && total === 0 ? (
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>No questions left</AlertTitle>
                <AlertDescription>All questions were deleted. Close and regenerate.</AlertDescription>
              </Alert>
            ) : null}

            {/* Question body */}
            {!isGenerating && currentQ ? (
              <div className="max-h-[55vh] overflow-y-auto space-y-4 py-1 pr-1">
                <div className="space-y-1.5">
                  <Label>Question</Label>
                  <textarea
                    value={currentQ.question}
                    onChange={(e) => updateQuestion(reviewPage, 'question', e.target.value)}
                    className="flex min-h-[72px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-none break-words"
                  />
                </div>

                {currentQ.type === 'mcq' ? (
                  <div className="space-y-2">
                    <Label>Options — click the radio to mark correct</Label>
                    {currentQ.options.map((opt, oi) => (
                      <div key={oi} className="flex items-start gap-2">
                        <input
                          type="radio"
                          name="correct-option"
                          checked={currentQ.correct_option_index === oi}
                          onChange={() => setCorrectOption(reviewPage, oi)}
                          className="mt-2.5 shrink-0 accent-primary"
                        />
                        <Input
                          value={opt}
                          onChange={(e) => updateOption(reviewPage, oi, e.target.value)}
                          className={`min-w-0 ${currentQ.correct_option_index === oi ? 'border-primary ring-1 ring-primary/30' : ''}`}
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    <Label>Model Answer</Label>
                    <textarea
                      value={currentQ.answer}
                      onChange={(e) => updateQuestion(reviewPage, 'answer', e.target.value)}
                      className="flex min-h-[72px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-none break-words"
                    />
                  </div>
                )}
              </div>
            ) : null}

            {!isGenerating && saveError ? (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Save failed</AlertTitle>
                <AlertDescription>{saveError}</AlertDescription>
              </Alert>
            ) : null}

            {!isGenerating ? (
              <DialogFooter className="flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                {/* Pagination */}
                <div className="flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="icon"
                    disabled={reviewPage === 0 || total === 0}
                    onClick={() => setReviewPage((p) => p - 1)}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="min-w-[3.5rem] text-center text-sm tabular-nums text-muted-foreground">
                    {total > 0 ? `${reviewPage + 1} / ${total}` : '—'}
                  </span>
                  <Button
                    variant="outline"
                    size="icon"
                    disabled={reviewPage >= total - 1 || total === 0}
                    onClick={() => setReviewPage((p) => p + 1)}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>

                {/* Save */}
                <Button onClick={handleSave} disabled={isSaving || total === 0}>
                  <CheckCircle className="mr-2 h-4 w-4" />
                  {isSaving ? 'Saving...' : `Save ${total} question${total === 1 ? '' : 's'}`}
                </Button>
              </DialogFooter>
            ) : null}
          </DialogContent>
        </Dialog>
        <Alert>
          <Sparkles className="h-4 w-4" />
          <AlertTitle>Exam created</AlertTitle>
          <AlertDescription>
            &ldquo;{createdExam.title}&rdquo; is live. Join code:{' '}
            <span className="font-mono font-semibold">{createdExam.join_code}</span>
          </AlertDescription>
        </Alert>

        <Card id="create-exam">
          <CardHeader>
            <div className="flex items-center justify-between gap-4">
              <div>
                <CardTitle>Generate AI Questions</CardTitle>
                <CardDescription>
                  Upload course material and let Veridex build the exam questions automatically.
                </CardDescription>
              </div>
              <Badge variant="default" className="gap-1">
                <Sparkles className="h-3.5 w-3.5" />
                Veridex
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            {aiError ? (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Error</AlertTitle>
                <AlertDescription>{aiError}</AlertDescription>
              </Alert>
            ) : null}

            {savedCount !== null ? (
              <Alert>
                <CheckCircle className="h-4 w-4" />
                <AlertTitle>Questions saved</AlertTitle>
                <AlertDescription>
                  {savedCount} question{savedCount === 1 ? '' : 's'} added to &ldquo;{createdExam.title}&rdquo;.
                </AlertDescription>
              </Alert>
            ) : null}

            {/* Step 1 – Upload */}
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                    uploadResult ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                  }`}
                >
                  1
                </span>
                <span className="text-sm font-semibold">Upload Course Material</span>
                {uploadResult ? (
                  <Badge variant="secondary" className="ml-auto">
                    {uploadResult.chunks_indexed} chunks indexed
                  </Badge>
                ) : null}
              </div>

              <div className="rounded-lg border-2 border-dashed border-border p-5 text-center">
                {uploadResult ? (
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-green-600 dark:text-green-400">Document ready</p>
                    <p className="text-xs text-muted-foreground">{uploadFile?.name}</p>
                  </div>
                ) : (
                  <>
                    <input
                      type="file"
                      id="course-material"
                      className="hidden"
                      accept=".pdf,.docx,.txt"
                      onChange={(event) => {
                        setUploadFile(event.target.files?.[0] ?? null);
                        // Reset prior upload result so the new file must be uploaded explicitly
                        setUploadResult(null);
                        setReviewQuestions(null);
                        setSavedCount(null);
                        setAiError(null);
                      }}
                    />
                    <label htmlFor="course-material" className="block cursor-pointer space-y-2">
                      <Upload className="mx-auto h-8 w-8 text-muted-foreground" />
                      <p className="text-sm font-medium">
                        {uploadFile ? uploadFile.name : 'Click to upload PDF, DOCX, or TXT'}
                      </p>
                      <p className="text-xs text-muted-foreground">Supported: PDF, DOCX, TXT — max 50 MB</p>
                    </label>
                    {uploadFile ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="mt-3"
                        onClick={handleUpload}
                        disabled={isUploading}
                      >
                        <Upload className="mr-2 h-3.5 w-3.5" />
                        {isUploading ? 'Uploading...' : 'Upload document'}
                      </Button>
                    ) : null}
                  </>
                )}
              </div>
            </div>

            {/* Step 2 – Configure & Generate */}
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                    uploadResult ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                  }`}
                >
                  2
                </span>
                <span className="text-sm font-semibold">Configure &amp; Generate</span>
              </div>

              <div className="grid gap-3 grid-cols-2">
                <div className="space-y-2">
                  <Label>Question Type</Label>
                  <Select
                    value={aiQuestionType}
                    onValueChange={(value) => setAiQuestionType(value as 'mcq' | 'open' | 'mixed')}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="mcq">Multiple Choice</SelectItem>
                      <SelectItem value="open">Open Ended</SelectItem>
                      <SelectItem value="mixed">Mixed</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Questions</Label>
                  <div className="flex h-10 items-center rounded-md border border-input bg-muted/40 px-3 text-sm text-muted-foreground">
                    {createdExam.question_count} (from exam settings)
                  </div>
                </div>
              </div>

              <Button onClick={handleGenerate} disabled={!uploadResult || isGenerating} className="w-full">
                <Sparkles className="mr-2 h-4 w-4" />
                {isGenerating ? 'Generating questions...' : 'Generate AI questions'}
              </Button>
            </div>

            <div className="border-t pt-4 text-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setCreatedExam(null);
                  setUploadFile(null);
                  setUploadResult(null);
                  setReviewQuestions(null);
                  setSavedCount(null);
                  setAiError(null);
                }}
              >
                <PlusCircle className="mr-2 h-3.5 w-3.5" />
                Create another exam
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── Phase 1: Exam creation form ──────────────────────────────────────────────
  return (
    <Card id="create-exam">
      <CardHeader>
        <div className="flex items-center justify-between gap-4">
          <div>
            <CardTitle>Create Exam</CardTitle>
            <CardDescription>
              Build an oral, written, or hybrid exam. New exams go live immediately, stay accessible by code until you
              close them, and support AI question generation after creation.
            </CardDescription>
          </div>
          <Badge variant="default" className="gap-1">
            <Sparkles className="h-3.5 w-3.5" />
            Veridex
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {errorMessage ? (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Unable to create exam</AlertTitle>
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        ) : null}

        {/* Basics */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 border-b pb-2">
            <BookOpen className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-semibold text-foreground">Basics</span>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="exam-title">
                Title <span className="text-destructive">*</span>
              </Label>
              <Input
                id="exam-title"
                placeholder="Object-Oriented Programming Oral"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="exam-subject">
                Subject <span className="text-destructive">*</span>
              </Label>
              <Input
                id="exam-subject"
                placeholder="Java, Algorithms, English"
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
              />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Exam Mode</Label>
              <Select value={examMode} onValueChange={(value) => setExamMode(value as CreateExamInput['examMode'])}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="oral">Oral</SelectItem>
                  <SelectItem value="written">Written</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Difficulty</Label>
              <Select
                value={difficultyLevel}
                onValueChange={(value) => setDifficultyLevel(value as CreateExamInput['difficultyLevel'])}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="beginner">Beginner</SelectItem>
                  <SelectItem value="intermediate">Intermediate</SelectItem>
                  <SelectItem value="advanced">Advanced</SelectItem>
                  <SelectItem value="mixed">Mixed</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 border-b pb-2">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-semibold text-foreground">Content</span>
          </div>
          <div className="space-y-2">
            <Label htmlFor="exam-description">Description</Label>
            <textarea
              id="exam-description"
              placeholder="Briefly describe the exam purpose and expected competencies."
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="exam-instructions">Student Instructions</Label>
            <textarea
              id="exam-instructions"
              placeholder="Tell students how the exam works and what they should prepare."
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            />
          </div>
        </div>

        {/* Settings */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 border-b pb-2">
            <Clock3 className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-semibold text-foreground">Settings</span>
          </div>
          <div className="grid gap-4 grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="duration-minutes">Duration (min)</Label>
              <Input
                id="duration-minutes"
                type="number"
                min={1}
                value={durationMinutes}
                onChange={(event) => setDurationMinutes(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="question-count">Questions</Label>
              <Input
                id="question-count"
                type="number"
                min={1}
                value={questionCount}
                onChange={(event) => setQuestionCount(event.target.value)}
              />
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between border-t pt-4">
          <p className="text-xs text-muted-foreground">Publishes immediately. AI questions can be added next.</p>
          <Button onClick={handleSubmit} disabled={isSubmitting}>
            <PlusCircle className="mr-2 h-4 w-4" />
            {isSubmitting ? 'Creating...' : 'Create exam'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

interface StudentJoinExamCardProps {
  onJoined: () => Promise<void>;
}

function StudentJoinExamCard({ onJoined }: StudentJoinExamCardProps) {
  const [joinCode, setJoinCode] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!joinCode.trim()) {
      setErrorMessage('Enter the exam join code first.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const response = await joinExam({ joinCode: joinCode.trim().toUpperCase() });
      setSuccessMessage(
        response.alreadyJoined
          ? `You are already enrolled in "${response.exam.title}".`
          : `Joined "${response.exam.title}" successfully.`,
      );
      setJoinCode('');
      await onJoined();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to join the exam.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Card id="join-exam">
      <CardHeader>
        <CardTitle>Join Exam</CardTitle>
        <CardDescription>Enter the code from your teacher to enroll in a private oral or written exam.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {errorMessage ? (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Unable to join</AlertTitle>
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        ) : null}

        {successMessage ? (
          <Alert>
            <ClipboardCheck className="h-4 w-4" />
            <AlertTitle>Enrollment updated</AlertTitle>
            <AlertDescription>{successMessage}</AlertDescription>
          </Alert>
        ) : null}

        <div className="space-y-2">
          <Label htmlFor="join-code">Join Code</Label>
          <Input
            id="join-code"
            placeholder="ABC123"
            value={joinCode}
            onChange={(event) => setJoinCode(event.target.value.toUpperCase())}
          />
        </div>

        <Button onClick={handleSubmit} disabled={isSubmitting}>
          <GraduationCap className="mr-2 h-4 w-4" />
          {isSubmitting ? 'Joining exam...' : 'Join exam'}
        </Button>
      </CardContent>
    </Card>
  );
}

interface ExamListSectionProps {
  role: UserRole;
  exams: Exam[];
  enrollments: ExamsListResponse['enrollments'];
}

function ExamListSection({ role, exams, enrollments }: ExamListSectionProps) {
  if (exams.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <BookOpen className="mx-auto mb-4 h-12 w-12 text-muted-foreground" />
          <h3 className="text-lg font-semibold">{isTeacherRole(role) ? 'No exams yet' : 'No joined exams yet'}</h3>
          <p className="mt-2 text-muted-foreground">
            {isTeacherRole(role)
              ? 'Create your first exam to start inviting students.'
              : 'Use a teacher join code to enroll in an exam and start a private attempt.'}
          </p>
        </CardContent>
      </Card>
    );
  }

  const enrollmentByExamId = new Map(enrollments.map((enrollment) => [enrollment.exam_id, enrollment]));

  return (
    <div className="space-y-4">
      {exams.map((exam) => {
        const enrollment = enrollmentByExamId.get(exam.id);

        return (
          <Card key={exam.id}>
            <CardContent className="p-6">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 flex-1 space-y-4">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div className="min-w-0">
                      <h3 className="truncate text-xl font-semibold">{exam.title}</h3>
                      <p className="text-muted-foreground">{exam.subject}</p>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <Badge variant={getExamStatusBadgeVariant(exam.status)}>{exam.status}</Badge>
                      <Badge variant="outline">{getExamModeLabel(exam.exam_mode)}</Badge>
                      {!isTeacherRole(role) && enrollment ? (
                        <Badge variant="secondary">{enrollment.status}</Badge>
                      ) : null}
                    </div>
                  </div>

                  {exam.description ? <p className="text-sm text-muted-foreground">{exam.description}</p> : null}

                  <div className="grid gap-3 text-sm text-muted-foreground md:grid-cols-2 xl:grid-cols-4">
                    <div className="flex items-center gap-2">
                      <Clock3 className="h-4 w-4" />
                      {formatDurationMinutes(exam.duration_minutes)}
                    </div>
                    <div className="flex items-center gap-2">
                      {exam.exam_mode === 'oral' ? <Mic className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
                      {exam.question_count} prompts
                    </div>
                    <div className="flex items-center gap-2">
                      <Users className="h-4 w-4" />
                      {exam.max_attempts_per_student} attempt{exam.max_attempts_per_student === 1 ? '' : 's'}
                    </div>
                    <div>
                      {exam.start_at
                        ? `Opens ${formatDateTime(exam.start_at)}`
                        : `Created ${formatDateTime(exam.created_at)}`}
                    </div>
                  </div>

                  {isTeacherRole(role) ? (
                    <div className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-3 text-sm">
                      <span className="font-medium">Join code:</span>{' '}
                      <span className="font-mono">{exam.join_code}</span>
                    </div>
                  ) : null}
                </div>

                <div className="flex items-center gap-3">
                  {isExamOpen(exam) ? (
                    <Badge variant="default">Open now</Badge>
                  ) : (
                    <Badge variant="outline">Not open</Badge>
                  )}
                  <Button asChild variant="outline">
                    <Link href={`/dashboard/exams/${exam.id}`}>
                      Open exam
                      <ExternalLink className="ml-2 h-4 w-4" />
                    </Link>
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function WorkspaceSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        {[1, 2, 3].map((item) => (
          <Card key={item}>
            <CardHeader className="pb-3">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-20" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-4 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>

      {[1, 2].map((item) => (
        <Card key={item}>
          <CardHeader>
            <Skeleton className="h-6 w-56" />
            <Skeleton className="h-4 w-full max-w-2xl" />
          </CardHeader>
          <CardContent className="space-y-4">
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-11 w-40" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function ExamWorkspace() {
  const [context, setContext] = useState<Awaited<ReturnType<typeof fetchExamContext>> | null>(null);
  const [examsResponse, setExamsResponse] = useState<ExamsListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const loadWorkspace = async () => {
    setErrorMessage(null);

    try {
      const nextContext = await fetchExamContext();
      setContext(nextContext);

      if (!nextContext.hasProfile || !nextContext.role) {
        setExamsResponse(null);
        return;
      }

      const nextExamsResponse = await fetchExams({ limit: 24 });
      setExamsResponse(nextExamsResponse);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to load the exam workspace.');
    }
  };

  useEffect(() => {
    const initializeWorkspace = async () => {
      try {
        await loadWorkspace();
      } finally {
        setIsLoading(false);
      }
    };

    void initializeWorkspace();
  }, []);

  const handleRefresh = async () => {
    setIsRefreshing(true);

    try {
      await loadWorkspace();
    } finally {
      setIsRefreshing(false);
    }
  };

  if (isLoading) {
    return <WorkspaceSkeleton />;
  }

  if (errorMessage) {
    return (
      <Card>
        <CardContent className="py-12">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Unable to load Veridex exams</AlertTitle>
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  if (!context?.hasProfile || !context.role) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Exam Profile Required</CardTitle>
          <CardDescription>
            The new Veridex exam workspace needs a profile in the new education domain.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            <GraduationCap className="h-4 w-4" />
            <AlertTitle>Profile not ready yet</AlertTitle>
            <AlertDescription>
              {context?.message || 'Finish onboarding to create your Veridex profile before using exams.'}
            </AlertDescription>
          </Alert>

          <p className="text-sm text-muted-foreground">
            Once your profile is saved, the exam workspace will unlock automatically.
          </p>
        </CardContent>
      </Card>
    );
  }

  const role = context.role;
  const exams = examsResponse?.exams ?? [];
  const enrollments = examsResponse?.enrollments ?? [];
  const isTeacher = isTeacherRole(role);

  const teacherPublishedCount = exams.filter((exam) => exam.status === 'published').length;
  const teacherOralCount = exams.filter((exam) => exam.exam_mode === 'oral').length;
  const studentOpenCount = exams.filter((exam) => isExamOpen(exam)).length;
  const studentOralCount = exams.filter((exam) => exam.exam_mode === 'oral').length;
  const firstName = context.context.profile?.full_name?.split(' ')[0] || 'there';

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <CardTitle className="text-2xl">Veridex Exam Workspace</CardTitle>
              <CardDescription className="mt-1 text-base">
                Welcome back, {firstName}. You are using the workspace as a {getRoleLabel(role).toLowerCase()}.
              </CardDescription>
            </div>
            <div className="flex items-center gap-3">
              <Badge variant="outline">{getRoleLabel(role)}</Badge>
              <Button variant="outline" onClick={handleRefresh} disabled={isRefreshing}>
                <RefreshCcw className="mr-2 h-4 w-4" />
                {isRefreshing ? 'Refreshing...' : 'Refresh'}
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        {isTeacher ? (
          <>
            <ExamSummaryCard
              label="Total Exams"
              value={exams.length}
              icon={<BookOpen className="h-5 w-5" />}
              hint="Teacher-owned exams in your workspace."
            />
            <ExamSummaryCard
              label="Published"
              value={teacherPublishedCount}
              icon={<ClipboardCheck className="h-5 w-5" />}
              hint="Ready for students to join when the schedule is open."
            />
            <ExamSummaryCard
              label="Oral Mode"
              value={teacherOralCount}
              icon={<Mic className="h-5 w-5" />}
              hint="Voice-first exams that can now launch into the Veridex oral room."
            />
          </>
        ) : (
          <>
            <ExamSummaryCard
              label="Joined Exams"
              value={exams.length}
              icon={<GraduationCap className="h-5 w-5" />}
              hint="Private teacher exam sessions you are enrolled in."
            />
            <ExamSummaryCard
              label="Open Now"
              value={studentOpenCount}
              icon={<Clock3 className="h-5 w-5" />}
              hint="Available to start or resume within the current exam window."
            />
            <ExamSummaryCard
              label="Oral Exams"
              value={studentOralCount}
              icon={<Mic className="h-5 w-5" />}
              hint="Voice-based exams that can open the live oral room."
            />
          </>
        )}
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>{isTeacher ? 'Exam Library' : 'My Exams'}</CardTitle>
              <CardDescription>
                {isTeacher
                  ? 'Review your published and draft exams, then open a detail page to inspect attempts.'
                  : 'Open any joined exam to read instructions, start a private attempt, or review prior submissions.'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ExamListSection role={role} exams={exams} enrollments={enrollments} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          {isTeacher ? (
            <TeacherCreateExamForm onCreated={loadWorkspace} />
          ) : (
            <StudentJoinExamCard onJoined={loadWorkspace} />
          )}

          <Card>
            <CardHeader>
              <CardTitle>{isTeacher ? 'Veridex Status' : 'What Works Right Now'}</CardTitle>
              <CardDescription>Frontend exam management is now wired to the new exam-domain API.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p>
                {isTeacher
                  ? 'You can create exams, share join codes, open exam detail pages, and evaluate student attempts from the dashboard.'
                  : 'You can join exams, open the exam brief, create a private attempt, and launch oral exams into the live Veridex room.'}
              </p>
              <p>
                Written flows now use a one-question-at-a-time attempt UI, hybrid flows still use manual attempt
                completion, and oral mode runs through the exam-aware websocket flow.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
