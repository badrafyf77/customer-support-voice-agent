'use client';

import { X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

interface LiveExamHeaderProps {
  examTitle: string;
  isConnected: boolean;
  onEnd: () => void;
  subtitle?: string;
  endLabel?: string;
}

export function LiveExamHeader({
  examTitle,
  isConnected,
  onEnd,
  subtitle = 'Live oral exam with an AI examiner.',
  endLabel = 'Exit Exam Room',
}: LiveExamHeaderProps) {
  return (
    <div className="mb-6 flex items-center justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold">{examTitle}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </div>

      <div className="flex items-center gap-3">
        {isConnected ? (
          <Badge variant="default" className="bg-green-600">
            <div className="mr-2 h-2 w-2 animate-pulse rounded-full bg-white" />
            Connected
          </Badge>
        ) : null}

        <Button variant="outline" size="sm" onClick={onEnd}>
          <X className="mr-2 h-4 w-4" />
          {endLabel}
        </Button>
      </div>
    </div>
  );
}
