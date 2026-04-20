'use client';

import { UserPlus, Target, Mic, BarChart3 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

const steps = [
  {
    icon: UserPlus,
    title: 'Create your profile',
    description: 'Sign up and complete your academic profile so Veridex can open the right teacher or student workspace.',
  },
  {
    icon: Target,
    title: 'Create or join an exam',
    description: 'Teachers publish exams with instructions and rubric criteria while students join securely with a code.',
  },
  {
    icon: Mic,
    title: 'Run the oral session',
    description: 'Students answer spoken questions in a live exam room while the AI examiner follows the loaded exam context.',
  },
  {
    icon: BarChart3,
    title: 'Review the attempt',
    description: 'Use transcripts, rubric scores, and evaluator summaries to review performance and next steps.',
  },
];

export function HowItWorksSection() {
  const [isVisible, setIsVisible] = useState(false);
  const sectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setIsVisible(true);
          }
        });
      },
      { threshold: 0.2 },
    );

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => observer.disconnect();
  }, []);

  return (
    <section className="mx-auto max-w-7xl px-[32px] py-24" ref={sectionRef}>
      <div className="text-center mb-20">
        <h2 className="text-[40px] leading-[44px] md:text-[56px] md:leading-[60px] tracking-[-1.2px] font-medium mb-6">
          How it works
        </h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
        {steps.map((step, index) => {
          const Icon = step.icon;
          return (
            <div
              key={index}
              className={`text-center transition-all duration-700 ${
                isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
              }`}
              style={{ transitionDelay: `${index * 150}ms` }}
            >
              <div className="w-16 h-16 rounded-2xl bg-muted/30 flex items-center justify-center mb-6 mx-auto hover:bg-muted/50 hover:scale-110 transition-all duration-300">
                <Icon className="w-8 h-8 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold mb-3">{step.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{step.description}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
