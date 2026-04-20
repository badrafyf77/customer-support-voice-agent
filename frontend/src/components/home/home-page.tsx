'use client';

import { createClient } from '@/utils/supabase/client';
import { useUserInfo } from '@/hooks/useUserInfo';
import '../../styles/home-page.css';
import Header from '@/components/home/header/header';
import { HeroSection } from '@/components/home/hero-section/hero-section';
import { FeaturesSection } from '@/components/home/features/features-section';
import { HowItWorksSection } from '@/components/home/how-it-works/how-it-works-section';
import { TestimonialsSection } from '@/components/home/testimonials/testimonials-section';
import { Pricing } from '@/components/home/pricing/pricing';
import { CTASection } from '@/components/home/cta/cta-section';
import { HomePageBackground } from '@/components/gradients/home-page-background';
import { Footer } from '@/components/home/footer/footer';

export function HomePage() {
  const supabase = createClient();
  const { user } = useUserInfo(supabase);
  const country = 'US';

  return (
    <>
      <div>
        <HomePageBackground />
        <Header user={user} />
        <HeroSection />
        <FeaturesSection />
        <HowItWorksSection />
        <TestimonialsSection />
        <Pricing country={country} />
        <CTASection />
        <Footer />
      </div>
    </>
  );
}
