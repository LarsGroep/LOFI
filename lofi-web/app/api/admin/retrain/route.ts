import { NextResponse } from 'next/server'

const GITHUB_OWNER = process.env.GITHUB_REPO_OWNER ?? 'LarsGroep'
const GITHUB_REPO = process.env.GITHUB_REPO_NAME ?? 'LOFI'
const WORKFLOW_FILE = 'retrain_xgboost.yml'

export async function POST(req: Request) {
  const token = process.env.GITHUB_TOKEN
  if (!token) {
    return NextResponse.json({ error: 'GITHUB_TOKEN not configured' }, { status: 500 })
  }

  let body: Record<string, string> = {}
  try { body = await req.json() } catch { /* no body */ }

  const dispatch = await fetch(
    `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ref: 'main',
        inputs: {
          push_predictions: body.push_predictions ?? 'true',
        },
      }),
    }
  )

  if (!dispatch.ok) {
    const text = await dispatch.text()
    return NextResponse.json({ error: `GitHub API error: ${dispatch.status}`, detail: text }, { status: 502 })
  }

  // 204 No Content on success — fetch the latest run to return its URL
  const runsRes = await fetch(
    `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/runs?per_page=1`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
    }
  )
  const runs = await runsRes.json()
  const runUrl = runs?.workflow_runs?.[0]?.html_url ?? null

  return NextResponse.json({ ok: true, runUrl })
}
