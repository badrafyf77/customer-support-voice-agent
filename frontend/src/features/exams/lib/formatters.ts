import type { BadgeProps } from '@/components/ui/badge';
import type { Exam, ExamAttempt, ExamAttemptStatus, ExamMode, ExamStatus, UserRole } from '@/lib/database.types';

function formatDate(value: string | null, options: Intl.DateTimeFormatOptions) {
  if (!value) {
    return 'Not scheduled';
  }

  const parsedDate = new Date(value);
  if (Number.isNaN(parsedDate.getTime())) {
    return 'Invalid date';
  }

  return new Intl.DateTimeFormat('en-US', options).format(parsedDate);
}

export function formatShortDate(value: string | null) {
  return formatDate(value, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatDateTime(value: string | null) {
  return formatDate(value, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function formatDurationMinutes(minutes: number | null) {
  if (minutes == null) {
    return 'Not set';
  }

  if (minutes < 60) {
    return `${minutes} min`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  if (remainingMinutes === 0) {
    return `${hours} hr`;
  }

  return `${hours} hr ${remainingMinutes} min`;
}

export function formatDurationSeconds(seconds: number | null) {
  if (seconds == null) {
    return 'In progress';
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;

  if (minutes === 0) {
    return `${remainingSeconds}s`;
  }

  return `${minutes}m ${remainingSeconds}s`;
}

export function getExamModeLabel(mode: ExamMode) {
  if (mode === 'oral') {
    return 'Oral';
  }

  if (mode === 'written') {
    return 'Written';
  }

  return 'Hybrid';
}

export function getExamStatusBadgeVariant(status: ExamStatus): BadgeProps['variant'] {
  if (status === 'published') {
    return 'default';
  }

  if (status === 'draft') {
    return 'secondary';
  }

  if (status === 'closed') {
    return 'outline';
  }

  return 'destructive';
}

export function getAttemptStatusBadgeVariant(status: ExamAttemptStatus): BadgeProps['variant'] {
  if (status === 'evaluated') {
    return 'default';
  }

  if (status === 'submitted') {
    return 'secondary';
  }

  if (status === 'in_progress') {
    return 'outline';
  }

  return 'destructive';
}

export function getScoreBadgeVariant(score: number | null): BadgeProps['variant'] {
  if (score == null) {
    return 'outline';
  }

  if (score >= 80) {
    return 'default';
  }

  if (score >= 60) {
    return 'secondary';
  }

  return 'destructive';
}

export function getRoleLabel(role: UserRole | null) {
  if (role === 'teacher') {
    return 'Teacher';
  }

  if (role === 'student') {
    return 'Student';
  }

  if (role === 'admin') {
    return 'Admin';
  }

  return 'Unassigned';
}

export function isExamOpen(exam: Exam) {
  if (exam.status === 'closed' || exam.status === 'archived') {
    return false;
  }

  return true;
}

export function countCompletedAttempts(attempts: ExamAttempt[]) {
  return attempts.filter((attempt) => attempt.status === 'submitted' || attempt.status === 'evaluated').length;
}
