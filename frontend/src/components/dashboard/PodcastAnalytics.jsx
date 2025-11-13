import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { makeApi } from '@/lib/apiClient';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export default function PodcastAnalytics({ podcastId, token, onBack }) {
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('30');
  const [showStats, setShowStats] = useState(null);
  const [episodesStats, setEpisodesStats] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (podcastId && token) {
      fetchAnalytics();
    }
  }, [podcastId, token, timeRange]);

  async function fetchAnalytics() {
    setLoading(true);
    setError(null);
    
    try {
      const api = makeApi(token);
      
      // Fetch show-level stats (includes top episodes now)
      const showData = await api.get(`/api/analytics/podcast/${podcastId}/downloads?days=${timeRange}`);
      setShowStats(showData);
      
      // Top episodes are now included in showData.top_episodes
      // No need for separate episodes-summary call
      setEpisodesStats(showData.top_episodes || []);
      
    } catch (err) {
      console.error('Failed to fetch analytics:', err);
      setError(err.message || 'Failed to load analytics data');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-8">
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto mb-4"></div>
            <p className="text-gray-600">Loading analytics...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight" style={{ color: '#2C3E50' }}>
            Podcast Analytics
          </h1>
          <Button variant="outline" onClick={onBack}>← Back</Button>
        </div>
        <Card className="shadow-sm border border-gray-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Analytics Not Available Yet</CardTitle>
            <CardDescription>Your podcast analytics will appear once episodes are downloaded by listeners</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-gray-700 space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <p className="font-medium text-blue-900 mb-2">📊 How Podcast Analytics Work</p>
              <p className="text-blue-800">Analytics data comes from OP3 (Open Podcast Prefix Project), which tracks downloads across all podcast apps.</p>
            </div>
            
            <div>
              <p className="font-medium text-gray-900 mb-2">If you're not seeing data yet, this is normal! Analytics appear when:</p>
              <ul className="list-disc list-inside ml-4 space-y-1 text-gray-600">
                <li>Your RSS feed has been published with episodes</li>
                <li>Listeners discover and download your episodes from podcast apps</li>
                <li>At least 24-48 hours have passed since your first downloads</li>
                <li>OP3 has processed the download data (updates daily)</li>
              </ul>
            </div>
            
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
              <p className="font-medium text-gray-900 mb-2">🚀 Quick Tips to Get Started:</p>
              <ul className="list-decimal list-inside ml-2 space-y-1 text-gray-600">
                <li>Share your podcast RSS feed on social media</li>
                <li>Submit to Apple Podcasts, Spotify, and other directories</li>
                <li>Test by downloading an episode yourself from a podcast app</li>
                <li>Check back in 24-48 hours to see your analytics</li>
              </ul>
            </div>
            
            <div className="flex gap-3 mt-6">
              <Button onClick={fetchAnalytics} variant="default">Check Again</Button>
              <Button variant="outline" onClick={onBack}>Back to Dashboard</Button>
            </div>
            
            {error && (
              <details className="mt-4">
                <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">Technical details</summary>
                <pre className="text-xs text-gray-500 mt-2 p-2 bg-gray-100 rounded overflow-x-auto">{error}</pre>
              </details>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  const downloadsData = showStats?.downloads_by_day || [];
  const topCountries = showStats?.top_countries || [];
  const topApps = showStats?.top_apps || [];
  
  // Check if we have any meaningful data
  const hasData = showStats && (
    showStats.downloads_all_time > 0 || 
    showStats.downloads_30d > 0 || 
    showStats.downloads_7d > 0 ||
    (showStats.top_episodes && showStats.top_episodes.length > 0)
  );

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight" style={{ color: '#2C3E50' }}>
            {showStats?.podcast_name || 'Podcast Analytics'}
          </h1>
          <p className="text-sm md:text-base text-gray-600 mt-1">Download statistics powered by OP3</p>
        </div>
        <div className="flex gap-3 items-center">
          <Select value={timeRange} onValueChange={setTimeRange}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Last 7 days</SelectItem>
              <SelectItem value="30">Last 30 days</SelectItem>
              <SelectItem value="90">Last 90 days</SelectItem>
              <SelectItem value="365">Last year</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={onBack}>Back</Button>
        </div>
      </div>

      {/* Summary Cards - Match dashboard style */}
      <Card className="shadow-sm border border-gray-200">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Download Statistics</CardTitle>
          <CardDescription>Download counts across different time periods</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-gray-700 space-y-4">
          {!hasData && (
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
              <p className="font-medium mb-1">Analytics data will appear after your RSS feed has been published and episodes have been downloaded by listeners.</p>
              {showStats?.note && (
                <p className="mt-1">{showStats.note}</p>
              )}
            </div>
          )}
          <div className="grid md:grid-cols-2 gap-3">
            <div className="p-3 rounded border bg-white flex flex-col gap-1">
              <span className="text-[11px] tracking-wide text-gray-500">Downloads Last 7 Days</span>
              <span className="text-lg font-semibold">{(showStats?.downloads_7d || 0).toLocaleString()}</span>
            </div>
            <div className="p-3 rounded border bg-white flex flex-col gap-1">
              <span className="text-[11px] tracking-wide text-gray-500">Downloads Last 30 Days</span>
              <span className="text-lg font-semibold">{(showStats?.downloads_30d || 0).toLocaleString()}</span>
            </div>
            <div className="p-3 rounded border bg-white flex flex-col gap-1">
              <span className="text-[11px] tracking-wide text-gray-500">Downloads Last Year</span>
              <span className="text-lg font-semibold">{(showStats?.downloads_365d || 0).toLocaleString()}</span>
            </div>
            <div className="p-3 rounded border bg-white flex flex-col gap-1">
              <span className="text-[11px] tracking-wide text-gray-500">All-Time Downloads</span>
              <span className="text-lg font-semibold">{(showStats?.downloads_all_time || 0).toLocaleString()}</span>
            </div>
          </div>
          <p className="text-[11px] text-gray-400">Analytics powered by OP3 (Open Podcast Prefix Project). Updates every 3 hours.</p>
        </CardContent>
      </Card>

      {/* Downloads Over Time Chart */}
      <Card className="shadow-sm border border-gray-200">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Downloads Over Time</CardTitle>
          <CardDescription>Daily download counts for the selected period</CardDescription>
        </CardHeader>
        <CardContent>
          {downloadsData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={downloadsData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="downloads" stroke="#8884d8" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center text-gray-500 py-12">No download data available</div>
          )}
        </CardContent>
      </Card>

      {/* Top Episodes Section - Match dashboard style */}
      {showStats?.top_episodes && showStats.top_episodes.length > 0 && (
        <Card className="shadow-sm border border-gray-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Top Episodes (All-Time)</CardTitle>
            <CardDescription>Your most popular episodes by all-time downloads</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-gray-700 space-y-4">
            <div className="space-y-2">
              {showStats.top_episodes.map((ep, idx) => (
                <div key={ep.episode_id || idx} className="p-3 rounded border bg-gradient-to-r from-blue-50 to-white flex items-center justify-between">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="text-[10px] px-1.5 py-0.5 border rounded font-semibold text-gray-600">#{idx + 1}</span>
                    <span className="text-[11px] tracking-wide text-gray-700 font-medium truncate" title={ep.title}>{ep.title}</span>
                  </div>
                  <div className="text-right ml-3">
                    <div className="text-base font-bold text-gray-900">{(ep.downloads_all_time || 0).toLocaleString()}</div>
                    <div className="text-[9px] text-gray-500">downloads</div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Two-column layout for geographic and app data */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Top Countries */}
        <Card className="shadow-sm border border-gray-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Top Countries</CardTitle>
            <CardDescription>Geographic distribution of listeners</CardDescription>
          </CardHeader>
          <CardContent>
            {topCountries.length > 0 ? (
              <div className="space-y-3">
                {topCountries.slice(0, 10).map((country, idx) => (
                  <div key={idx} className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-700">{country.country || 'Unknown'}</span>
                    <div className="flex items-center gap-3">
                      <div className="w-32 bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-blue-600 h-2 rounded-full"
                          style={{
                            width: `${(country.downloads / topCountries[0].downloads) * 100}%`
                          }}
                        />
                      </div>
                      <span className="text-sm text-gray-600 w-16 text-right">
                        {country.downloads.toLocaleString()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center text-gray-500 py-8">No geographic data available yet</div>
            )}
          </CardContent>
        </Card>

        {/* Top Podcast Apps */}
        <Card className="shadow-sm border border-gray-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Top Podcast Apps</CardTitle>
            <CardDescription>Where listeners are tuning in</CardDescription>
          </CardHeader>
          <CardContent>
            {topApps.length > 0 ? (
              <div className="space-y-3">
                {topApps.slice(0, 10).map((app, idx) => (
                  <div key={idx} className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-700">{app.app || 'Unknown'}</span>
                    <div className="flex items-center gap-3">
                      <div className="w-32 bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-green-600 h-2 rounded-full"
                          style={{
                            width: `${(app.downloads / topApps[0].downloads) * 100}%`
                          }}
                        />
                      </div>
                      <span className="text-sm text-gray-600 w-16 text-right">
                        {app.downloads.toLocaleString()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center text-gray-500 py-8">No app data available</div>
            )}
          </CardContent>
        </Card>
      </div>

    </div>
  );
}
