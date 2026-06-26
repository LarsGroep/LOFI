import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url)
    const search = searchParams.get('q') ?? ''
    const limit = Math.min(Number(searchParams.get('limit') ?? 60), 200)

    const supabase = createServiceClient()
    let query = supabase
      .from('youtube_sets')
      .select('*')
      .order('published_at', { ascending: false })
      .limit(limit)

    if (search) {
      query = query.ilike('title', `%${search}%`)
    }

    const { data, error } = await query
    if (error) throw error
    return NextResponse.json(data ?? [])
  } catch (err) {
    console.error('[GET /api/youtube]', err)
    return NextResponse.json({ error: 'Failed to fetch youtube sets' }, { status: 500 })
  }
}
