'use client';

import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, FileText } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import type { ExamQuestion, ExamWrittenAnswer } from '../types';

interface WrittenExamQuestionFlowProps {
  questions: ExamQuestion[];
  initialAnswers: ExamWrittenAnswer[];
  isSubmitting: boolean;
  onSubmit: (writtenAnswers: ExamWrittenAnswer[]) => Promise<void>;
  onCancelAttempt: () => Promise<void>;
}

function buildInitialAnswerMap(questions: ExamQuestion[], writtenAnswers: ExamWrittenAnswer[]) {
  const answerByQuestionId = new Map<string, string>();
  const answerByQuestionText = new Map<string, string>();
  const orderedAnswers: string[] = [];

  for (const writtenAnswer of writtenAnswers) {
    const answerText = (writtenAnswer.student_answer ?? writtenAnswer.answer ?? '').trim();
    orderedAnswers.push(answerText);

    const questionId = writtenAnswer.question_id?.trim();
    if (questionId) {
      answerByQuestionId.set(questionId, answerText);
    }

    const questionText = writtenAnswer.question_text?.trim();
    if (questionText) {
      answerByQuestionText.set(questionText, answerText);
    }
  }

  const nextAnswerMap: Record<string, string> = {};

  for (const [index, question] of questions.entries()) {
    const answerFromId = answerByQuestionId.get(question.id);
    const answerFromText = answerByQuestionText.get(question.question_text.trim());
    const answerFromOrder = orderedAnswers[index];

    nextAnswerMap[question.id] = answerFromId ?? answerFromText ?? answerFromOrder ?? '';
  }

  return nextAnswerMap;
}

export function WrittenExamQuestionFlow({
  questions,
  initialAnswers,
  isSubmitting,
  onSubmit,
  onCancelAttempt,
}: WrittenExamQuestionFlowProps) {
  const writtenQuestions = useMemo(
    () =>
      questions
        .filter((question) => question.question_type === 'qcm' || question.question_type === 'libre')
        .sort((left, right) => left.question_order - right.question_order),
    [questions],
  );

  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [answersByQuestionId, setAnswersByQuestionId] = useState<Record<string, string>>({});
  const [localErrorMessage, setLocalErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    setAnswersByQuestionId(buildInitialAnswerMap(writtenQuestions, initialAnswers));
    setCurrentQuestionIndex(0);
    setLocalErrorMessage(null);
  }, [writtenQuestions, initialAnswers]);

  const currentQuestion = writtenQuestions[currentQuestionIndex] || null;

  const answeredCount = writtenQuestions.filter((question) => {
    const answerText = answersByQuestionId[question.id] || '';
    return answerText.trim().length > 0;
  }).length;

  const isCurrentQuestionAnswered =
    currentQuestion != null && (answersByQuestionId[currentQuestion.id] || '').trim().length > 0;

  const completionPercentage =
    writtenQuestions.length > 0 ? Math.round((answeredCount / writtenQuestions.length) * 100) : 0;

  const updateCurrentAnswer = (nextAnswer: string) => {
    if (!currentQuestion) {
      return;
    }

    setAnswersByQuestionId((currentState) => ({
      ...currentState,
      [currentQuestion.id]: nextAnswer,
    }));

    if (localErrorMessage) {
      setLocalErrorMessage(null);
    }
  };

  const goToNextQuestion = () => {
    if (!currentQuestion) {
      return;
    }

    if (!isCurrentQuestionAnswered) {
      setLocalErrorMessage('Please answer this question before moving to the next one.');
      return;
    }

    setLocalErrorMessage(null);
    setCurrentQuestionIndex((index) => Math.min(index + 1, writtenQuestions.length - 1));
  };

  const goToPreviousQuestion = () => {
    setLocalErrorMessage(null);
    setCurrentQuestionIndex((index) => Math.max(index - 1, 0));
  };

  const handleSubmitAttempt = async () => {
    if (!currentQuestion) {
      return;
    }

    const missingQuestionOrders = writtenQuestions
      .filter((question) => (answersByQuestionId[question.id] || '').trim().length === 0)
      .map((question) => question.question_order);

    if (missingQuestionOrders.length > 0) {
      setLocalErrorMessage(
        `Every question must be answered before submission. Missing: ${missingQuestionOrders.join(', ')}.`,
      );
      return;
    }

    const payload: ExamWrittenAnswer[] = writtenQuestions.map((question) => {
      const answerText = (answersByQuestionId[question.id] || '').trim();

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
      };
    });

    setLocalErrorMessage(null);
    await onSubmit(payload);
  };

  if (writtenQuestions.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Written Exam Unavailable</CardTitle>
          <CardDescription>No generated written questions are linked to this exam yet.</CardDescription>
        </CardHeader>
        <CardContent>
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>No questions found</AlertTitle>
            <AlertDescription>
              The teacher must generate and save question rows in exam_questions before this written attempt can be
              answered.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const isLastQuestion = currentQuestionIndex === writtenQuestions.length - 1;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Written Exam Questions
            </CardTitle>
            <CardDescription>
              Answer one question at a time. All answers will be submitted together when you finish the last question.
            </CardDescription>
          </div>
          <Badge variant="outline">
            {answeredCount}/{writtenQuestions.length} answered
          </Badge>
        </div>

        <div className="space-y-2 pt-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Progress</span>
            <span>{completionPercentage}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${completionPercentage}%` }}
            />
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {localErrorMessage ? (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Answer required</AlertTitle>
            <AlertDescription>{localErrorMessage}</AlertDescription>
          </Alert>
        ) : null}

        {currentQuestion ? (
          <div className="space-y-4 rounded-lg border border-border p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">Question {currentQuestion.question_order}</Badge>
              <Badge variant="outline">{currentQuestion.question_type.toUpperCase()}</Badge>
              <Badge variant="outline">{currentQuestion.max_points} points</Badge>
              {isCurrentQuestionAnswered ? (
                <Badge variant="default">
                  <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
                  Answered
                </Badge>
              ) : null}
            </div>

            <p className="text-base font-medium leading-relaxed">{currentQuestion.question_text}</p>

            {currentQuestion.question_type === 'qcm' &&
            currentQuestion.choices &&
            currentQuestion.choices.length > 0 ? (
              <div className="space-y-2">
                <Label>Select one answer</Label>
                <div className="grid gap-2">
                  {currentQuestion.choices.map((choice) => {
                    const isSelected = (answersByQuestionId[currentQuestion.id] || '') === choice;
                    return (
                      <button
                        key={`${currentQuestion.id}-${choice}`}
                        type="button"
                        onClick={() => updateCurrentAnswer(choice)}
                        className={`rounded-md border px-3 py-2 text-left text-sm transition ${
                          isSelected
                            ? 'border-primary bg-primary/10 text-foreground'
                            : 'border-border bg-background hover:bg-muted/40'
                        }`}
                      >
                        {choice}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor={`written-answer-${currentQuestion.id}`}>Your answer</Label>
                <textarea
                  id={`written-answer-${currentQuestion.id}`}
                  value={answersByQuestionId[currentQuestion.id] || ''}
                  onChange={(event) => updateCurrentAnswer(event.target.value)}
                  placeholder="Write your answer here..."
                  className="flex min-h-[180px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>
            )}
          </div>
        ) : null}

        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={goToPreviousQuestion}
              disabled={isSubmitting || currentQuestionIndex === 0}
            >
              Previous
            </Button>

            {!isLastQuestion ? (
              <Button onClick={goToNextQuestion} disabled={isSubmitting}>
                Next question
              </Button>
            ) : (
              <Button onClick={handleSubmitAttempt} disabled={isSubmitting}>
                {isSubmitting ? 'Submitting...' : 'Submit written attempt'}
              </Button>
            )}
          </div>

          <Button variant="ghost" onClick={onCancelAttempt} disabled={isSubmitting}>
            Cancel attempt
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
