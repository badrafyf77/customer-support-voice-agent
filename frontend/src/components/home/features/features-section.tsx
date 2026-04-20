'use client';

import { Mic, FileText, Zap, BarChart3, Calendar, Target } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

const features = [
  {
    icon: Mic,
    title: 'AI oral exam sessions',
    description:
      'Run live oral exams with a realtime AI examiner that asks one question at a time and keeps the session structured.',
  },
  {
    icon: Target,
    title: 'Teacher-aligned questioning',
    description:
      'Questions adapt to the exam subject, teacher instructions, difficulty, and rubric so each session stays on target.',
  },
  {
    icon: FileText,
    title: 'Live transcripts',
    description:
      'Capture every answer in real time so you can review phrasing, clarity, and structure after each session.',
  },
  {
    icon: Calendar,
    title: 'Scheduled exam windows',
    description: 'Publish exams with timing, attempt rules, and join codes that fit real classroom workflows.',
  },
  {
    icon: BarChart3,
    title: 'Rubric scoring',
    description: 'Track rubric scores, evaluator summaries, and detailed attempt records for every student.',
  },
  {
    icon: Zap,
    title: 'Fast evaluation loops',
    description: 'Review oral exam results quickly with transcripts, criterion scores, and actionable feedback.',
  },
];

export function FeaturesSection() {
  const [visibleItems, setVisibleItems] = useState<number[]>([]);
  const sectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            features.forEach((_, index) => {
              setTimeout(() => {
                setVisibleItems((prev) => [...prev, index]);
              }, index * 100);
            });
          }
        });
      },
      { threshold: 0.1 },
    );

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => observer.disconnect();
  }, []);

  return (
    <section id="features" className="mx-auto max-w-7xl px-[32px] py-24" ref={sectionRef}>
      <div className="text-center mb-20">
        <h2 className="text-[40px] leading-[44px] md:text-[56px] md:leading-[60px] tracking-[-1.2px] font-medium mb-6">
          Build smarter assessments
        </h2>
        <p className="text-[18px] leading-[27px] text-muted-foreground max-w-2xl mx-auto">
          Everything you need to create, deliver, and review AI-assisted exams in one workspace.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {features.map((feature, index) => {
          const Icon = feature.icon;
          const isVisible = visibleItems.includes(index);
          return (
            <div
              key={index}
              className={`group transition-all duration-700 ${
                isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
              }`}
            >
              <div className="w-14 h-14 rounded-xl bg-muted/30 flex items-center justify-center mb-6 group-hover:bg-muted/50 group-hover:scale-110 transition-all duration-300">
                <Icon className="w-7 h-7 text-muted-foreground" />
              </div>
              <h3 className="text-xl font-semibold mb-3">{feature.title}</h3>
              <p className="text-base leading-relaxed text-muted-foreground">{feature.description}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
