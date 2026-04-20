import Link from 'next/link';
import { Mail } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { LoginGradient } from '@/components/gradients/login-gradient';
import { LoginCardGradient } from '@/components/gradients/login-card-gradient';
import '../../../styles/login.css';

interface ConfirmSignupPageProps {
  searchParams: Promise<{
    email?: string;
  }>;
}

export default async function ConfirmSignupPage({ searchParams }: ConfirmSignupPageProps) {
  const { email } = await searchParams;

  return (
    <div>
      <LoginGradient />
      <div className="flex min-h-screen items-center justify-center px-4">
        <Card className="relative w-full max-w-md overflow-hidden bg-background/80 backdrop-blur-[6px]">
          <LoginCardGradient />
          <CardHeader className="relative z-10 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
              <Mail className="h-7 w-7 text-primary" />
            </div>
            <CardTitle className="text-2xl">Confirm your email</CardTitle>
            <CardDescription className="text-base">
              We sent a confirmation link to{' '}
              <span className="font-medium text-foreground">{email || 'your inbox'}</span>.
            </CardDescription>
          </CardHeader>

          <CardContent className="relative z-10 space-y-4 text-center">
            <p className="text-sm text-muted-foreground">
              You will not be able to access onboarding, upload your CV, or use the dashboard until you confirm your
              email address.
            </p>

            <p className="text-sm text-muted-foreground">
              After you click the link in the email, you will be sent back to onboarding automatically.
            </p>

            <div className="flex flex-col gap-3">
              <Button asChild variant="secondary">
                <Link href="/login">Go to login</Link>
              </Button>
              <Button asChild variant="outline">
                <Link href="/signup">Use a different email</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
