'use client';

import Link from 'next/link';
import { useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  BellRing,
  CheckCircle2,
  ClipboardCheck,
  Eye,
  LoaderIcon,
  Radio,
  ShieldCheck,
} from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { TeacherEvaluationSheet } from './teacher-evaluation-sheet';
import {
  formatDateTime,
  getAttemptStatusBadgeVariant,
  getExamModeLabel,
  getScoreBadgeVariant,
} from '../lib/formatters';
import { useRealtimeEvaluations } from '../hooks/use-realtime-evaluations';
import type { EvaluationListItem } from '../types';

function SummaryCard({ title, value, hint }: { title: string; value: string | number; hint: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-3xl">{value}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0 text-sm text-muted-foreground">{hint}</CardContent>
    </Card>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        {[1, 2, 3].map((item) => (
          <Skeleton key={item} className="h-32 w-full" />
        ))}
      </div>
      <Skeleton className="h-96 w-full" />
    </div>
  );
}

// ── Teacher evaluation table row ──────────────────────────────────────────────

interface EvalRowProps {
  item: EvaluationListItem;
  onViewDetails: (id: string) => void;
}

function EvalTableRow({ item, onViewDetails }: EvalRowProps) {
  return (
    <TableRow>
      <TableCell>
        <div>
          <p className="font-medium">{item.student_name || 'Unknown student'}</p>
          <p className="text-xs text-muted-foreground truncate max-w-[180px]">{item.student_user_id}</p>
        </div>
      </TableCell>
      <TableCell>
        <div>
          <p className="font-medium">{item.exam_title}</p>
          <p className="text-xs text-muted-foreground">{getExamModeLabel(item.exam_mode)}</p>
        </div>
      </TableCell>
      <TableCell>
        <Badge variant={getAttemptStatusBadgeVariant(item.status as never)}>{item.status}</Badge>
      </TableCell>
      <TableCell>
        {item.score_summary.max_total_score > 0 ? (
          <div className="space-y-1">
            <Badge variant={getScoreBadgeVariant(item.score_summary.percentage)}>
              {item.score_summary.percentage.toFixed(1)}%
            </Badge>
            <p className="text-xs text-muted-foreground">
              {item.score_summary.total_score}/{item.score_summary.max_total_score} pts
            </p>
          </div>
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-1.5 text-sm">
          <CheckCircle2 className="h-3.5 w-3.5 text-muted-foreground" />
          <span>{item.question_results_count}</span>
        </div>
      </TableCell>
      <TableCell>
        {item.pending_contestations > 0 ? (
          <Badge variant="destructive" className="gap-1">
            <BellRing className="h-3 w-3" />
            {item.pending_contestations}
          </Badge>
        ) : (
          <span className="text-sm text-muted-foreground">0</span>
        )}
      </TableCell>
      <TableCell>{formatDateTime(item.updated_at)}</TableCell>
      <TableCell className="text-right">
        <div className="flex items-center justify-end gap-2">
          <Button size="sm" variant="secondary" onClick={() => onViewDetails(item.evaluation_id)}>
            <Eye className="mr-1.5 h-3.5 w-3.5" />
            Details
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href={`/dashboard/exams/attempts/${item.evaluation_id}`}>
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

// ── Teacher dashboard ─────────────────────────────────────────────────────────

function TeacherDashboard({
  evaluations,
  isRefreshing,
}: {
  evaluations: EvaluationListItem[];
  isRefreshing: boolean;
}) {
  const [selectedAttemptId, setSelectedAttemptId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const openDetails = (id: string) => {
    setSelectedAttemptId(id);
    setSheetOpen(true);
  };

  const liveItems = evaluations.filter((e) => e.status === 'submitted' || e.status === 'in_progress');
  const completedItems = evaluations.filter((e) => e.status === 'evaluated');
  const needsReviewItems = evaluations.filter((e) => e.pending_contestations > 0);

  const liveCount = liveItems.length;
  const doneCount = completedItems.length;
  const pendingContestCount = evaluations.reduce((sum, item) => sum + item.pending_contestations, 0);

  const renderTable = (rows: EvaluationListItem[], emptyLabel: string) => (
    <Card>
      <CardContent className="pt-4">
        {rows.length === 0 ? (
          <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">{emptyLabel}</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Student</TableHead>
                <TableHead>Exam</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Score</TableHead>
                <TableHead>Questions</TableHead>
                <TableHead>Reclamations</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((item) => (
                <EvalTableRow key={item.evaluation_id} item={item} onViewDetails={openDetails} />
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );

  return (
    <>
      <div className="space-y-6">
        <div className="grid gap-4 md:grid-cols-3">
          <SummaryCard title="Live now" value={liveCount} hint="Attempts currently being evaluated." />
          <SummaryCard title="Completed" value={doneCount} hint="Evaluations with final scores published." />
          <SummaryCard title="Pending reclamations" value={pendingContestCount} hint="Student disputes waiting for your decision." />
        </div>

        <Tabs defaultValue="all" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <TabsList>
              <TabsTrigger value="all">
                All
                <Badge variant="secondary" className="ml-1.5 h-4 px-1.5 text-xs">{evaluations.length}</Badge>
              </TabsTrigger>
              <TabsTrigger value="live">
                Live
                {liveCount > 0 && <Badge variant="secondary" className="ml-1.5 h-4 px-1.5 text-xs">{liveCount}</Badge>}
              </TabsTrigger>
              <TabsTrigger value="completed">
                Completed
                {doneCount > 0 && <Badge variant="secondary" className="ml-1.5 h-4 px-1.5 text-xs">{doneCount}</Badge>}
              </TabsTrigger>
              <TabsTrigger value="review">
                Needs Review
                {pendingContestCount > 0 && (
                  <Badge variant="destructive" className="ml-1.5 h-4 px-1.5 text-xs">{pendingContestCount}</Badge>
                )}
              </TabsTrigger>
            </TabsList>

            {isRefreshing ? (
              <Badge variant="outline">
                <LoaderIcon className="mr-1 h-3.5 w-3.5 animate-spin" />
                Realtime sync
              </Badge>
            ) : (
              <Badge variant="outline">
                <Radio className="mr-1 h-3.5 w-3.5" />
                Supabase Realtime connected
              </Badge>
            )}
          </div>

          <TabsContent value="all" className="mt-0">
            <Card>
              <CardHeader>
                <CardTitle>All Evaluations</CardTitle>
                <CardDescription>
                  Click <strong>Details</strong> to review and edit an evaluation inline, or the arrow to open the full attempt page.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {evaluations.length === 0 ? (
                  <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                    No evaluations yet. Trigger an attempt evaluation to see it appear here live.
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Student</TableHead>
                        <TableHead>Exam</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Score</TableHead>
                        <TableHead>Questions</TableHead>
                        <TableHead>Reclamations</TableHead>
                        <TableHead>Updated</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {evaluations.map((item) => (
                        <EvalTableRow key={item.evaluation_id} item={item} onViewDetails={openDetails} />
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="live" className="mt-0">
            {renderTable(liveItems, 'No live evaluations right now.')}
          </TabsContent>

          <TabsContent value="completed" className="mt-0">
            {renderTable(completedItems, 'No completed evaluations yet.')}
          </TabsContent>

          <TabsContent value="review" className="mt-0">
            <Card>
              <CardHeader>
                <CardTitle>Needs Review</CardTitle>
                <CardDescription>
                  These evaluations have pending student reclamations. Open the detail sheet to approve, reject, or manually edit each one.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {needsReviewItems.length === 0 ? (
                  <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                    No pending reclamations right now.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {needsReviewItems.map((item) => (
                      <div key={`review-${item.evaluation_id}`} className="rounded-xl border border-border bg-background/70 p-5">
                        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                          <div className="space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="destructive">
                                <BellRing className="mr-1 h-3.5 w-3.5" />
                                {item.pending_contestations} pending
                              </Badge>
                              <Badge variant="outline">{item.student_name || 'Unknown student'}</Badge>
                              <Badge variant="outline">{getExamModeLabel(item.exam_mode)}</Badge>
                            </div>
                            <p className="text-lg font-semibold">{item.exam_title}</p>
                            <p className="text-sm text-muted-foreground">Last updated {formatDateTime(item.updated_at)}</p>
                          </div>
                          <div className="flex gap-2">
                            <Button size="sm" variant="secondary" onClick={() => openDetails(item.evaluation_id)}>
                              <Eye className="mr-1.5 h-3.5 w-3.5" />
                              Review in detail
                            </Button>
                            <Button asChild size="sm" variant="outline">
                              <Link href={`/dashboard/exams/attempts/${item.evaluation_id}`}>
                                <ClipboardCheck className="mr-1.5 h-3.5 w-3.5" />
                                Full page
                              </Link>
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>

      <TeacherEvaluationSheet
        attemptId={selectedAttemptId}
        open={sheetOpen}
        onOpenChange={(open) => {
          setSheetOpen(open);
          if (!open) setSelectedAttemptId(null);
        }}
      />
    </>
  );
}

// ── Student dashboard ─────────────────────────────────────────────────────────

function StudentDashboard({
  evaluations,
  isRefreshing,
}: {
  evaluations: EvaluationListItem[];
  isRefreshing: boolean;
}) {
  const liveCount = evaluations.filter((e) => e.status === 'submitted').length;
  const doneCount = evaluations.filter((e) => e.status === 'evaluated').length;
  const pendingContestCount = evaluations.reduce((sum, item) => sum + item.pending_contestations, 0);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <SummaryCard title="Live evaluations" value={liveCount} hint="Attempts still being evaluated in real time." />
        <SummaryCard title="Completed" value={doneCount} hint="Attempts with final scores available now." />
        <SummaryCard title="Needs attention" value={pendingContestCount} hint="Reclamation items waiting for teacher review." />
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>My Evaluations</CardTitle>
              <CardDescription>Open any attempt to watch streaming results or review the final evaluation.</CardDescription>
            </div>
            {isRefreshing ? (
              <Badge variant="outline">
                <LoaderIcon className="mr-1 h-3.5 w-3.5 animate-spin" />
                Live refresh
              </Badge>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {evaluations.length === 0 ? (
            <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
              No evaluations yet. Start or submit an exam attempt to see it appear here.
            </div>
          ) : null}

          {evaluations.map((item) => (
            <div key={item.evaluation_id} className="rounded-xl border border-border bg-background/70 p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={getAttemptStatusBadgeVariant(item.status as never)}>{item.status}</Badge>
                    <Badge variant="outline">{getExamModeLabel(item.exam_mode)}</Badge>
                    {item.overall_score != null ? (
                      <Badge variant={getScoreBadgeVariant(item.overall_score)}>{item.overall_score}%</Badge>
                    ) : null}
                    {item.pending_contestations > 0 ? (
                      <Badge variant="secondary">
                        <BellRing className="mr-1 h-3 w-3" />
                        {item.pending_contestations} reclamation
                      </Badge>
                    ) : null}
                  </div>
                  <div>
                    <p className="text-lg font-semibold">{item.exam_title}</p>
                    <p className="text-sm text-muted-foreground">Updated {formatDateTime(item.updated_at)}</p>
                  </div>
                </div>
                <Button asChild>
                  <Link href={`/dashboard/exams/attempts/${item.evaluation_id}`}>
                    Open attempt
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Link>
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Root component ────────────────────────────────────────────────────────────

export function EvaluationsDashboard() {
  const { context, evaluationsResponse, isLoading, isRefreshing, errorMessage } = useRealtimeEvaluations();

  if (isLoading) return <DashboardSkeleton />;

  if (errorMessage) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Evaluations unavailable</AlertTitle>
        <AlertDescription>{errorMessage}</AlertDescription>
      </Alert>
    );
  }

  if (!context?.hasProfile || !context.role || !evaluationsResponse) {
    return (
      <Alert>
        <ShieldCheck className="h-4 w-4" />
        <AlertTitle>Profile required</AlertTitle>
        <AlertDescription>Complete the Veridex profile flow before opening the live evaluations dashboard.</AlertDescription>
      </Alert>
    );
  }

  const evaluations = evaluationsResponse.evaluations || [];
  const isTeacher = context.role === 'teacher' || context.role === 'admin';

  if (!isTeacher) {
    return <StudentDashboard evaluations={evaluations} isRefreshing={isRefreshing} />;
  }

  return <TeacherDashboard evaluations={evaluations} isRefreshing={isRefreshing} />;
}
