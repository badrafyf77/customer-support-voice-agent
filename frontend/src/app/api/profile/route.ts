import { NextRequest, NextResponse } from 'next/server';
import { createClient as createAdminClient } from '@/utils/supabase/server-internal';
import { createClient as createSessionClient } from '@/utils/supabase/server';

const ALLOWED_ROLES = ['teacher', 'student', 'admin'] as const;

type AllowedRole = (typeof ALLOWED_ROLES)[number];

function normalizeRole(value: unknown, fallback: AllowedRole = 'student'): AllowedRole {
  if (typeof value === 'string') {
    const normalizedValue = value.trim().toLowerCase();
    if (ALLOWED_ROLES.includes(normalizedValue as AllowedRole)) {
      return normalizedValue as AllowedRole;
    }
  }

  return fallback;
}

function buildProfileResponse(profile: {
  full_name: string;
  email: string;
  role: AllowedRole;
  institution_name: string | null;
  department: string | null;
  academic_level: string | null;
  field_of_study: string | null;
  bio: string | null;
}) {
  return {
    full_name: profile.full_name,
    email: profile.email,
    role: profile.role,
    institution_name: profile.institution_name || '',
    department: profile.department || '',
    academic_level: profile.academic_level || '',
    field_of_study: profile.field_of_study || '',
    bio: profile.bio || '',
  };
}

// GET - Fetch user profile
export async function GET() {
  try {
    const sessionSupabase = await createSessionClient();

    const {
      data: { user },
      error: authError,
    } = await sessionSupabase.auth.getUser();

    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Get user profile
    const { data: profiles, error } = await sessionSupabase
      .from('profiles')
      .select('*')
      .eq('user_id', user.id)
      .limit(1);

    if (error) {
      console.error('Error fetching profile:', error);
      return NextResponse.json({ error: 'Failed to fetch profile' }, { status: 500 });
    }

    const storedProfile = profiles?.[0] ?? null;
    const profile = buildProfileResponse({
      full_name: storedProfile?.full_name || user.user_metadata?.full_name || user.user_metadata?.name || '',
      email: storedProfile?.email || user.email || '',
      role: normalizeRole(storedProfile?.role || user.user_metadata?.role, 'student'),
      institution_name: storedProfile?.institution_name || null,
      department: storedProfile?.department || null,
      academic_level: storedProfile?.academic_level || null,
      field_of_study: storedProfile?.field_of_study || null,
      bio: storedProfile?.bio || null,
    });

    return NextResponse.json({ profile, hasProfile: Boolean(storedProfile) });
  } catch (error) {
    console.error('Error in GET /api/profile:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

// POST - Create or update user profile
export async function POST(request: NextRequest) {
  try {
    const sessionSupabase = await createSessionClient();
    const canUseAdminClient = Boolean(process.env.SUPABASE_SERVICE_ROLE_KEY?.trim());

    const {
      data: { user },
      error: authError,
    } = await sessionSupabase.auth.getUser();

    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();
    const { full_name, email, role, institution_name, department, academic_level, field_of_study, bio } = body;

    // Validate required fields
    if (!full_name) {
      return NextResponse.json({ error: 'full_name is required' }, { status: 400 });
    }

    // Check if profile exists
    const { data: existingProfiles, error: existingProfileError } = await sessionSupabase
      .from('profiles')
      .select('id, role')
      .eq('user_id', user.id)
      .limit(1);

    if (existingProfileError) {
      console.error('Error checking existing profile:', existingProfileError);
      return NextResponse.json({ error: 'Failed to load existing profile' }, { status: 500 });
    }

    const existingProfile = existingProfiles?.[0] ?? null;
    const nextRole = normalizeRole(role, normalizeRole(existingProfile?.role, 'student'));

    let profile;
    let isNew = false;

    if (existingProfile) {
      // Update existing profile
      const { data, error } = await sessionSupabase
        .from('profiles')
        .update({
          full_name,
          email: email || user.email || '',
          role: nextRole,
          institution_name: institution_name || null,
          department: department || null,
          academic_level: academic_level || null,
          field_of_study: field_of_study || null,
          bio: bio || null,
        })
        .eq('user_id', user.id)
        .select()
        .single();

      if (error) {
        console.error('Error updating profile:', error);
        return NextResponse.json(
          {
            error: 'Failed to update profile',
            details: error.message,
            code: error.code,
          },
          { status: 500 },
        );
      }

      profile = data;
    } else {
      // Create new profile
      const { data, error } = await sessionSupabase
        .from('profiles')
        .insert({
          user_id: user.id,
          role: nextRole,
          full_name,
          email: email || user.email || '',
          institution_name: institution_name || null,
          department: department || null,
          academic_level: academic_level || null,
          field_of_study: field_of_study || null,
          bio: bio || null,
        })
        .select()
        .single();

      if (error) {
        console.error('Error creating profile:', error);
        return NextResponse.json(
          {
            error: 'Failed to create profile',
            details: error.message,
            code: error.code,
          },
          { status: 500 },
        );
      }

      profile = data;
      isNew = true;
    }

    if (canUseAdminClient) {
      const adminSupabase = await createAdminClient();
      const { error: metadataError } = await adminSupabase.auth.admin.updateUserById(user.id, {
        user_metadata: {
          role: nextRole,
          full_name,
        },
      });

      if (metadataError) {
        console.error('Error updating auth metadata:', metadataError);
      }
    }

    return NextResponse.json({
      success: true,
      profile: buildProfileResponse(profile),
      hasProfile: true,
      message: isNew ? 'Profile created successfully' : 'Profile updated successfully',
    });
  } catch (error: unknown) {
    console.error('Error in POST /api/profile:', error);
    return NextResponse.json(
      {
        error: 'Internal server error',
        message: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 },
    );
  }
}
