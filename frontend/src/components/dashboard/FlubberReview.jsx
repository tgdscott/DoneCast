import { useEffect, useState } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/card'
import { Button } from '../ui/button'
import { Checkbox } from '../ui/checkbox'
import { Loader2, Scissors, RefreshCw } from 'lucide-react'
import { makeApi } from '@/lib/apiClient'

export default function FlubberReview({ episodeId, token, onClose }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [contexts, setContexts] = useState([])
  const [selected, setSelected] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)

  const load = async () => {
    if (!episodeId) return
    setLoading(true); setError(''); setResult(null)
    try {
  const api = makeApi(token)
  const data = await api.get(`/api/flubber/contexts/${episodeId}`)
      setContexts(data.contexts || [])
      const pre = {}
      data.contexts?.forEach(c => { pre[c.flubber_index] = true })
      setSelected(pre)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(()=> { load() }, [episodeId])

  const toggle = (idx) => setSelected(cur => ({ ...cur, [idx]: !cur[idx] }))

  const submitCuts = async () => {
    const cuts = contexts.filter(c => selected[c.flubber_index]).map(c => ({
      start_s: Math.max(0, c.flubber_time_s - 0.75),
      end_s: c.computed_end_s ?? ((c.flubber_end_s || c.flubber_time_s) + 0.25),
    }))
    if (!cuts.length) { setError('No cuts selected'); return }
    setSubmitting(true); setError(''); setResult(null)
    try {
  const api = makeApi(token)
  const data = await api.post(`/api/flubber/apply/${episodeId}`, cuts)
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const prepare = async () => {
    if (!episodeId) return
    setLoading(true); setError('')
    try {
  const api = makeApi(token)
  await api.post(`/api/flubber/prepare/${episodeId}`, {})
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="mt-4">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Review Flubber Markers</CardTitle>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={prepare} disabled={loading}><Scissors className="w-4 h-4 mr-1"/>Find Markers</Button>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}><RefreshCw className="w-4 h-4 mr-1"/>Reload</Button>
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading && <div className="flex items-center gap-2 text-sm text-gray-600"><Loader2 className="w-4 h-4 animate-spin"/> Loading contexts...</div>}
        {error && <div className="text-sm text-red-600">{error}</div>}
        {!loading && !error && contexts.length === 0 && <div className="text-xs text-gray-500">No flubber contexts found.</div>}
        {!loading && contexts.length > 0 && (
          <div className="space-y-3">
            {contexts.map(ctx => (
              <div key={ctx.flubber_index} className="border rounded p-2 flex flex-col gap-2 bg-white">
                <div className="flex items-center justify-between">
                  <div className="text-xs">Around {Math.floor(ctx.flubber_time_s)} seconds</div>
                  <label className="flex items-center gap-1 text-xs cursor-pointer">
                    <Checkbox checked={!!selected[ctx.flubber_index]} onCheckedChange={()=>toggle(ctx.flubber_index)} /> Cut
                  </label>
                </div>
                <audio controls className="w-full" src={ctx.url} preload="metadata" />
              </div>
            ))}
          </div>
        )}
        {contexts.length > 0 && (
          <div className="flex items-center gap-3">
            <Button onClick={submitCuts} disabled={submitting} className="flex items-center gap-1">
              {submitting ? <Loader2 className="w-4 h-4 animate-spin"/> : <Scissors className="w-4 h-4"/>}
              {submitting ? 'Applying...' : 'Apply Selected Cuts'}
            </Button>
            {result && <div className="text-xs text-green-600">Removed {(result.removed_ms/1000).toFixed(2)}s → {result.cleaned_audio_new}</div>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
