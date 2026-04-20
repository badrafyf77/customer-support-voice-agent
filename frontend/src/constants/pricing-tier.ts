export interface Tier {
  name: string;
  id: 'starter' | 'pro' | 'advanced';
  icon: string;
  description: string;
  features: string[];
  featured: boolean;
  priceId: Record<string, string>;
}

export const PricingTier: Tier[] = [
  {
    name: 'Starter',
    id: 'starter',
    icon: '/assets/icons/price-tiers/free-icon.svg',
    description: 'Great for small classes starting with AI-assisted oral and written exams.',
    features: ['1 exam workspace', 'Teacher and student roles', 'Core transcript and scoring tools'],
    featured: false,
    priceId: { month: 'pri_01k8f86h5w4skg8bh570rdhtnd', year: 'pri_01k8f8ay73x5c2mdja0g8kfb4h' },
  },
  {
    name: 'Pro',
    id: 'pro',
    icon: '/assets/icons/price-tiers/basic-icon.svg',
    description: 'Built for departments that need more scale, flexibility, and exam review capacity.',
    features: ['Unlimited exam workspaces', 'Advanced rubric workflows', 'More instructor collaboration', 'Everything in Starter'],
    featured: true,
    priceId: { month: 'pri_01k8f8442bf14dapvt9zqq1297', year: 'pri_01k8f8bvgy8yvyk5gpd7ky6ahp' },
  },
  {
    name: 'Advanced',
    id: 'advanced',
    icon: '/assets/icons/price-tiers/pro-icon.svg',
    description: 'Designed for institutions that need governance, customization, and larger-scale deployment.',
    features: [
      'Single sign on (SSO)',
      'Institution-wide administration',
      'Priority support',
      'Custom rollout support',
      'Everything in Pro',
    ],
    featured: false,
    priceId: { month: 'pri_01k8f85y5wzf5yxvvkfbzcp30z', year: 'pri_01k8f8cqssgasrvmbxz6mcmr0e' },
  },
];
