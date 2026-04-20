'use client';

import { useEffect, useRef, useState } from 'react';

const testimonials = [
  {
    name: 'Sarah Johnson',
    role: 'Lecturer',
    company: 'Faculty of Science',
    text: 'The oral exam flow feels structured and fair. I can publish an exam quickly and still review detailed attempt feedback afterwards.',
  },
  {
    name: 'Michael Chen',
    role: 'Student',
    company: 'Computer Science',
    text: 'The live transcript helped me understand exactly where my explanations became weak during the exam.',
  },
  {
    name: 'Emily Rodriguez',
    role: 'Department Coordinator',
    company: 'Engineering School',
    text: 'Join codes and private attempts made it much easier to organize oral assessments without exposing student work.',
  },
  {
    name: 'David Kim',
    role: 'Student',
    company: 'Mathematics',
    text: 'The follow-up questions forced me to justify each answer instead of memorizing short responses.',
  },
  {
    name: 'Jessica Martinez',
    role: 'Teacher',
    company: 'Business School',
    text: 'Rubric scoring gives me a strong first pass, and I can still adjust feedback manually when needed.',
  },
  {
    name: 'Alex Thompson',
    role: 'Student',
    company: 'Physics',
    text: 'This became my go-to platform before oral assessments because the feedback is specific and easy to act on.',
  },
];

export function TestimonialsSection() {
  const [visibleItems, setVisibleItems] = useState<number[]>([]);
  const sectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            testimonials.forEach((_, index) => {
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
    <section className="mx-auto max-w-7xl px-[32px] py-24" ref={sectionRef}>
      <div className="text-center mb-20">
        <h2 className="text-[40px] leading-[44px] md:text-[56px] md:leading-[60px] tracking-[-1.2px] font-medium mb-6">
          Learners love us!
        </h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {testimonials.map((testimonial, index) => {
          const isVisible = visibleItems.includes(index);
          return (
            <div
              key={index}
              className={`border border-border/50 rounded-lg p-6 bg-background/50 hover:border-border hover:bg-background/70 transition-all duration-700 ${
                isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
              }`}
            >
              <p className="text-base leading-relaxed mb-6">{testimonial.text}</p>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-muted/50 flex items-center justify-center text-sm font-semibold">
                  {testimonial.name.charAt(0)}
                </div>
                <div>
                  <div className="font-semibold text-sm">{testimonial.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {testimonial.role}, {testimonial.company}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
