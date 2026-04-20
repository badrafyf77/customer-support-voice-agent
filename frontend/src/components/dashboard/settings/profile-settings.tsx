'use client';

import { useEffect, useState } from 'react';
import { LoaderIcon } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import type { UserRole } from '@/lib/database.types';

type ProfileFormState = {
  full_name: string;
  email: string;
  role: UserRole;
  institution_name: string;
  department: string;
  academic_level: string;
  field_of_study: string;
  bio: string;
};

const EMPTY_PROFILE: ProfileFormState = {
  full_name: '',
  email: '',
  role: 'student',
  institution_name: '',
  department: '',
  academic_level: '',
  field_of_study: '',
  bio: '',
};

export function ProfileSettings() {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [profile, setProfile] = useState<ProfileFormState>(EMPTY_PROFILE);

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const response = await fetch('/api/profile');
        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.error || 'Failed to load profile');
        }

        if (data.profile) {
          setProfile({
            full_name: data.profile.full_name || '',
            email: data.profile.email || '',
            role: data.profile.role || 'student',
            institution_name: data.profile.institution_name || '',
            department: data.profile.department || '',
            academic_level: data.profile.academic_level || '',
            field_of_study: data.profile.field_of_study || '',
            bio: data.profile.bio || '',
          });
        }
      } catch (error) {
        console.error('Error fetching profile:', error);
        toast({
          description: 'Failed to load profile',
          variant: 'destructive',
        });
      } finally {
        setIsLoading(false);
      }
    };

    void fetchProfile();
  }, [toast]);

  const handleSave = async () => {
    setIsSaving(true);

    try {
      const response = await fetch('/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profile),
      });

      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload.error || 'Failed to save profile');
      }

      toast({
        description: 'Profile updated successfully!',
      });
    } catch (error) {
      console.error('Error saving profile:', error);
      toast({
        description: error instanceof Error ? error.message : 'Failed to save profile',
        variant: 'destructive',
      });
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <LoaderIcon className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Identity</CardTitle>
          <CardDescription>How Veridex identifies you in the exam workspace.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="full_name">Full Name</Label>
            <Input
              id="full_name"
              value={profile.full_name}
              onChange={(event) => setProfile((prev) => ({ ...prev, full_name: event.target.value }))}
            />
          </div>

          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={profile.email}
              onChange={(event) => setProfile((prev) => ({ ...prev, email: event.target.value }))}
            />
          </div>

          <div className="grid gap-3">
            <Label>Role</Label>
            <div className="grid gap-3 md:grid-cols-2">
              <button
                type="button"
                onClick={() => setProfile((prev) => ({ ...prev, role: 'student' }))}
                className={`rounded-lg border px-4 py-4 text-left transition-colors ${
                  profile.role === 'student' ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/50'
                }`}
              >
                <div className="mb-2 font-medium">Student</div>
                <p className="text-sm text-muted-foreground">Join exams and complete private attempts.</p>
              </button>

              <button
                type="button"
                onClick={() => setProfile((prev) => ({ ...prev, role: 'teacher' }))}
                className={`rounded-lg border px-4 py-4 text-left transition-colors ${
                  profile.role === 'teacher' ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/50'
                }`}
              >
                <div className="mb-2 font-medium">Teacher</div>
                <p className="text-sm text-muted-foreground">Create exams, publish codes, and review attempts.</p>
              </button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Academic Profile</CardTitle>
          <CardDescription>Update the context Veridex uses for exam and classroom workflows.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="institution_name">Institution</Label>
            <Input
              id="institution_name"
              value={profile.institution_name}
              onChange={(event) => setProfile((prev) => ({ ...prev, institution_name: event.target.value }))}
            />
          </div>

          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="department">{profile.role === 'teacher' ? 'Department or Module' : 'Department or Track'}</Label>
            <Input
              id="department"
              value={profile.department}
              onChange={(event) => setProfile((prev) => ({ ...prev, department: event.target.value }))}
            />
          </div>

          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="academic_level">{profile.role === 'teacher' ? 'Teaching Level' : 'Academic Level'}</Label>
            <Input
              id="academic_level"
              value={profile.academic_level}
              onChange={(event) => setProfile((prev) => ({ ...prev, academic_level: event.target.value }))}
            />
          </div>

          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="field_of_study">{profile.role === 'teacher' ? 'Subject Area' : 'Field of Study'}</Label>
            <Input
              id="field_of_study"
              value={profile.field_of_study}
              onChange={(event) => setProfile((prev) => ({ ...prev, field_of_study: event.target.value }))}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Bio</CardTitle>
          <CardDescription>Optional context you want attached to your Veridex profile.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <textarea
            value={profile.bio}
            onChange={(event) => setProfile((prev) => ({ ...prev, bio: event.target.value }))}
            placeholder="Tell Veridex a little more about your teaching context, learning goals, or exam environment."
            className="min-h-36 w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
          />

          <Button onClick={handleSave} disabled={isSaving} size="lg">
            {isSaving ? (
              <>
                <LoaderIcon className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              'Save Changes'
            )}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
