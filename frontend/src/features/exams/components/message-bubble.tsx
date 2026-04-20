'use client';

import { Bot, User } from 'lucide-react';

interface RenderableTranscriptMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  type: 'partial' | 'final';
  timestamp: number;
}

interface MessageBubbleProps {
  message: RenderableTranscriptMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isAssistant = message.role === 'assistant';
  const isPartial = message.type === 'partial';

  return (
    <div className={`flex gap-3 ${isAssistant ? 'justify-start' : 'justify-end'}`}>
      {isAssistant ? (
        <div className="flex-shrink-0">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10">
            <Bot className="h-4 w-4 text-primary" />
          </div>
        </div>
      ) : null}

      <div className={`flex max-w-[80%] flex-col ${isAssistant ? 'items-start' : 'items-end'}`}>
        <div
          className={`rounded-lg px-4 py-2.5 ${
            isAssistant ? 'bg-muted text-foreground' : 'bg-primary text-primary-foreground'
          } ${isPartial ? 'opacity-70' : 'opacity-100'}`}
        >
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{message.content}</p>

          {isPartial ? (
            <div className="mt-2 flex items-center gap-1">
              <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
              <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" style={{ animationDelay: '0.2s' }} />
              <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" style={{ animationDelay: '0.4s' }} />
            </div>
          ) : null}
        </div>

        <span className="mt-1 text-xs text-muted-foreground">
          {new Date(message.timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      </div>

      {!isAssistant ? (
        <div className="flex-shrink-0">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10">
            <User className="h-4 w-4 text-primary" />
          </div>
        </div>
      ) : null}
    </div>
  );
}
