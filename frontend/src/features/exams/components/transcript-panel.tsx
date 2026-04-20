'use client';

import { useEffect, useRef, useState } from 'react';
import { MessageSquare } from 'lucide-react';
import { MessageBubble } from './message-bubble';

interface TranscriptPanelProps {
  messages: Array<{
    id: string;
    role: 'user' | 'assistant';
    content: string;
    type: 'partial' | 'final';
    timestamp: number;
  }>;
  emptySecondaryText?: string;
}

export function TranscriptPanel({
  messages,
  emptySecondaryText = 'Start speaking to begin the oral exam.',
}: TranscriptPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollTimeoutRef = useRef<number | null>(null);
  const shouldAutoScrollRef = useRef(true);
  const [isUserScrolling, setIsUserScrolling] = useState(false);

  const updateAutoScrollPreference = () => {
    if (!scrollRef.current) {
      return;
    }

    const element = scrollRef.current;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom <= 48;
  };

  useEffect(() => {
    if (!scrollRef.current || isUserScrolling || !shouldAutoScrollRef.current) {
      return;
    }

    window.setTimeout(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }, 50);
  }, [isUserScrolling, messages]);

  const handleScroll = () => {
    updateAutoScrollPreference();
    setIsUserScrolling(true);

    if (scrollTimeoutRef.current != null) {
      window.clearTimeout(scrollTimeoutRef.current);
    }

    scrollTimeoutRef.current = window.setTimeout(() => {
      setIsUserScrolling(false);
    }, 1_000);
  };

  return (
    <div className="flex h-[500px] flex-col">
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <div className="text-center">
              <MessageSquare className="mx-auto mb-3 h-12 w-12 opacity-50" />
              <p className="text-sm">Conversation will appear here.</p>
              <p className="mt-1 text-xs">{emptySecondaryText}</p>
            </div>
          </div>
        ) : (
          messages.map((message) => <MessageBubble key={message.id} message={message} />)
        )}
      </div>
    </div>
  );
}
