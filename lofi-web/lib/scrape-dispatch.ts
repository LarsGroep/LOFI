const GITHUB_OWNER = process.env.GITHUB_REPO_OWNER ?? 'LarsGroep'
const GITHUB_REPO = process.env.GITHUB_REPO_NAME ?? 'LOFI'
const WORKFLOW_FILE = 'scrape_flagged.yml'

// Same normalisation as scrapers/queue_similar_artists.py::_slug — slugs must
// collide with the Python-generated ones so UNIQUE(slug) catches duplicates.
export function slugify(name: string): string {
  return name
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

// Fire-and-forget dispatch of the scrape workflow for a single artist.
// Returns false when GITHUB_TOKEN is missing or the dispatch fails — the artist
// stays flagged needs_scraping and the nightly run picks it up instead.
export async function dispatchArtistScrape(artistId: string): Promise<boolean> {
  const token = process.env.GITHUB_TOKEN
  if (!token) return false
  try {
    const res = await fetch(
      `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ref: 'main', inputs: { artist_id: artistId } }),
      }
    )
    if (!res.ok) console.error('[dispatchArtistScrape]', res.status, await res.text())
    return res.ok
  } catch (err) {
    console.error('[dispatchArtistScrape]', err)
    return false
  }
}
