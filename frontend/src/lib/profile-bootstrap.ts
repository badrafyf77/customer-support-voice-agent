import type { User } from '@supabase/supabase-js';
import type { UserRole } from '@/lib/database.types';

const ALLOWED_ROLES: readonly UserRole[] = ['teacher', 'student', 'admin'];

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function toTitleCase(value: string): string {
  return value
    .split(' ')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ');
}

export function normalizeUserRole(value: unknown, fallback: UserRole = 'student'): UserRole {
  if (typeof value === 'string') {
    const normalizedValue = value.trim().toLowerCase() as UserRole;
    if (ALLOWED_ROLES.includes(normalizedValue)) {
      return normalizedValue;
    }
  }

  return fallback;
}

export function getBootstrapFullName(user: Pick<User, 'email' | 'user_metadata'>): string {
  if (isNonEmptyString(user.user_metadata?.full_name)) {
    return user.user_metadata.full_name.trim();
  }

  if (isNonEmptyString(user.user_metadata?.name)) {
    return user.user_metadata.name.trim();
  }

  if (isNonEmptyString(user.email)) {
    const localPart = user.email.split('@')[0]?.trim() || '';
    const normalizedLocalPart = localPart
      .replace(/[._-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    if (normalizedLocalPart.length > 0) {
      return toTitleCase(normalizedLocalPart);
    }
  }

  return 'Veridex User';
}

export function getBootstrapEmail(user: Pick<User, 'id' | 'email'>): string {
  if (isNonEmptyString(user.email)) {
    return user.email.trim();
  }

  return `veridex+${user.id}@local.invalid`;
}

export function buildBootstrapProfile(user: Pick<User, 'id' | 'email' | 'user_metadata'>) {
  return {
    user_id: user.id,
    role: normalizeUserRole(user.user_metadata?.role),
    full_name: getBootstrapFullName(user),
    email: getBootstrapEmail(user),
  };
}
