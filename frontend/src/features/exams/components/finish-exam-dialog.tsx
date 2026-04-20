'use client';

import { AlertTriangle, CheckCircle } from 'lucide-react';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface FinishExamDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  title?: string;
  introText?: string;
  followUpText?: string;
  checklistItems?: string[];
  confirmLabel?: string;
}

export function FinishExamDialog({
  open,
  onOpenChange,
  onConfirm,
  title = 'Finish Oral Exam?',
  introText = 'Are you sure you want to finish this oral exam?',
  followUpText = 'Veridex will evaluate the attempt and you will not be able to continue afterwards.',
  checklistItems = [
    'Subject mastery evaluation',
    'Communication and clarity review',
    'Reasoning and accuracy scoring',
    'Private attempt storage under the shared exam',
  ],
  confirmLabel = 'Yes, Finish Oral Exam',
}: FinishExamDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-yellow-100 dark:bg-yellow-900/20">
              <AlertTriangle className="h-5 w-5 text-yellow-600 dark:text-yellow-500" />
            </div>
            {title}
          </DialogTitle>

          <div className="pt-4 text-base leading-relaxed text-muted-foreground">
            <p>{introText}</p>
            <p className="mt-2">{followUpText}</p>
            <ul className="mt-3 list-inside list-disc space-y-1 text-sm">
              {checklistItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </DialogHeader>

        <DialogFooter className="mt-4 gap-2 sm:gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="flex-1 sm:flex-none">
            Cancel
          </Button>
          <Button onClick={onConfirm} className="flex-1 bg-green-600 hover:bg-green-700 sm:flex-none">
            <CheckCircle className="mr-2 h-4 w-4" />
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
