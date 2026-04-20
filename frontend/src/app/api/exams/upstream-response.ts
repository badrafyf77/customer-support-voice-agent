type ValidationIssue = {
  loc?: unknown[];
  msg?: string;
};

function formatValidationIssues(detail: unknown): string | null {
  if (!Array.isArray(detail)) {
    return null;
  }

  const issues = detail
    .map((issue) => {
      if (!issue || typeof issue !== 'object') {
        return null;
      }

      const candidate = issue as ValidationIssue;
      const message = typeof candidate.msg === 'string' ? candidate.msg : null;
      const location = Array.isArray(candidate.loc)
        ? candidate.loc
            .filter((part) => typeof part === 'string' || typeof part === 'number')
            .join('.')
        : '';

      if (!message) {
        return null;
      }

      return location ? `${location}: ${message}` : message;
    })
    .filter((issue): issue is string => Boolean(issue));

  return issues.length > 0 ? issues.join('; ') : null;
}

function extractErrorMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') {
    return null;
  }

  const record = payload as {
    error?: unknown;
    message?: unknown;
    detail?: unknown;
  };

  if (typeof record.error === 'string' && record.error.trim()) {
    return record.error;
  }

  if (typeof record.message === 'string' && record.message.trim()) {
    return record.message;
  }

  if (typeof record.detail === 'string' && record.detail.trim()) {
    return record.detail;
  }

  return formatValidationIssues(record.detail);
}

export async function readUpstreamResponse(response: Response): Promise<unknown> {
  const raw = await response.text();

  if (!raw) {
    return response.ok ? {} : { error: `Upstream service returned ${response.status} with an empty response body.` };
  }

  try {
    const parsed = JSON.parse(raw) as unknown;
    const error = extractErrorMessage(parsed);

    if (!response.ok && error && typeof parsed === 'object' && parsed !== null) {
      return { ...(parsed as Record<string, unknown>), error };
    }

    return parsed;
  } catch {
    const contentType = response.headers.get('content-type') ?? 'unknown';
    const preview = raw.replace(/\s+/g, ' ').trim().slice(0, 180);
    const error = response.ok
      ? `Upstream service returned non-JSON content (${contentType}).`
      : `Upstream service returned ${response.status} ${response.statusText} as non-JSON content (${contentType}).`;

    console.error('Non-JSON upstream response', {
      status: response.status,
      statusText: response.statusText,
      contentType,
      preview,
    });

    return { error, preview };
  }
}
