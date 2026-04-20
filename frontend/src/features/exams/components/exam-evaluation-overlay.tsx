'use client';

import { LoaderIcon } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

interface ExamEvaluationOverlayProps {
  visible: boolean;
  message: string;
  title?: string;
  fallbackMessage?: string;
}

export function ExamEvaluationOverlay({
  visible,
  message,
  title = 'Evaluating Your Oral Exam',
  fallbackMessage = 'Please wait while Veridex analyzes your oral exam attempt.',
}: ExamEvaluationOverlayProps) {
  if (!visible) {
    return null;
  }

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <Card className="w-full max-w-md">
        <CardContent className="pt-6">
          <div className="flex flex-col items-center gap-4">
            <LoaderIcon className="h-12 w-12 animate-spin text-primary" />
            <div className="text-center">
              <h3 className="text-lg font-semibold">{title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{message || fallbackMessage}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
