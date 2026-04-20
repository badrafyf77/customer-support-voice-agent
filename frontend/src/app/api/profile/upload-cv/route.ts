import { NextResponse } from 'next/server';

const ORASENSE_CV_MESSAGE =
  'Resume/CV uploads are no longer part of Veridex. Use the education profile fields instead.';

export async function POST() {
  return NextResponse.json(
    {
      error: ORASENSE_CV_MESSAGE,
    },
    { status: 410 },
  );
}

export async function DELETE() {
  return NextResponse.json(
    {
      error: ORASENSE_CV_MESSAGE,
    },
    { status: 410 },
  );
}
