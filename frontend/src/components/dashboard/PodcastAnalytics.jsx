import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { makeApi } from '@/lib/apiClient';
import { BarChart, TrendingUp, Globe, Smartphone, Download, Calendar } from 'lucide-react';
import { LineChart, Line, BarChart as RechartsBar, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D'];

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
      <div className="container mx-auto p-6">
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
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-between mb-6">
          <Button variant="outline" onClick={onBack}>← Back</Button>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Analytics Not Available Yet</CardTitle>
            <CardDescription>Your podcast analytics will appear once episodes are downloaded by listeners</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4 text-sm text-gray-600">
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <p className="font-medium text-blue-900 mb-2">📊 How Podcast Analytics Work</p>
                <p className="text-blue-800">Analytics data comes from OP3 (Open Podcast Prefix Project), which tracks downloads across all podcast apps.</p>
              </div>
              
              <div>
                <p className="font-medium text-gray-900 mb-2">If you're not seeing data yet, this is normal! Analytics appear when:</p>
                <ul className="list-disc list-inside ml-4 space-y-1">
                  <li>Your RSS feed has been published with episodes</li>
                  <li>Listeners discover and download your episodes from podcast apps</li>
                  <li>At least 24-48 hours have passed since your first downloads</li>
                  <li>OP3 has processed the download data (updates daily)</li>
                </ul>
              </div>
              
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                <p className="font-medium text-gray-900 mb-2">🚀 Quick Tips to Get Started:</p>
                <ul className="list-decimal list-inside ml-2 space-y-1">
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
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const totalDownloads = showStats?.total_downloads || 0;
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
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">{showStats?.podcast_name || 'Podcast Analytics'}</h1>
          <p className="text-gray-600 mt-1">Download statistics powered by OP3</p>
          {!hasData && showStats?.note && (
            <p className="text-sm text-amber-600 mt-2">💡 {showStats.note}</p>
          )}
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

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
              <Download className="w-4 h-4" />
              Last 7 Days
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{(showStats?.downloads_7d || 0).toLocaleString()}</div>
            <p className="text-xs text-gray-500 mt-1">Weekly downloads</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
              <Calendar className="w-4 h-4" />
              Last 30 Days
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{(showStats?.downloads_30d || 0).toLocaleString()}</div>
            <p className="text-xs text-gray-500 mt-1">Monthly downloads</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              Last Year
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{(showStats?.downloads_365d || 0).toLocaleString()}</div>
            <p className="text-xs text-gray-500 mt-1">Yearly downloads</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
              <BarChart className="w-4 h-4" />
              All-Time
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{(showStats?.downloads_all_time || 0).toLocaleString()}</div>
            <p className="text-xs text-gray-500 mt-1">Total downloads</p>
          </CardContent>
        </Card>
      </div>

      {/* Downloads Over Time Chart */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart className="w-5 h-5" />
            Downloads Over Time
          </CardTitle>
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

      {/* Top Episodes Section */}
      {showStats?.top_episodes && showStats.top_episodes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5" />
              Top Performing Episodes
            </CardTitle>
            <CardDescription>Your most popular episodes by all-time downloads</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {showStats.top_episodes.map((ep, idx) => (
                <div key={ep.episode_id || idx} className="border rounded-lg p-4 hover:shadow-md transition-shadow">
                  <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center text-white font-bold text-sm">
                      #{idx + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="font-semibold text-gray-900 mb-2 truncate" title={ep.title}>{ep.title}</h4>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                        <div className="bg-gray-50 p-2 rounded">
                          <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1">Last 24h</div>
                          <div className="font-semibold text-gray-900">{(ep.downloads_1d || 0).toLocaleString()}</div>
                        </div>
                        <div className="bg-gray-50 p-2 rounded">
                          <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1">Last 7d</div>
                          <div className="font-semibold text-gray-900">{(ep.downloads_7d || 0).toLocaleString()}</div>
                        </div>
                        <div className="bg-gray-50 p-2 rounded">
                          <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1">Last 30d</div>
                          <div className="font-semibold text-gray-900">{(ep.downloads_30d || 0).toLocaleString()}</div>
                        </div>
                        <div className="bg-blue-50 p-2 rounded col-span-2 md:col-span-2">
                          <div className="text-[10px] text-blue-600 uppercase tracking-wide mb-1 font-semibold">All-Time</div>
                          <div className="font-bold text-blue-900 text-lg">{(ep.downloads_all_time || 0).toLocaleString()}</div>
                        </div>
                      </div>
                    </div>
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
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Globe className="w-5 h-5" />
              Top Countries
            </CardTitle>
            <CardDescription>Geographic distribution of listeners</CardDescription>
          </CardHeader>
          <CardContent>
            {topCountries.length > 0 ? (
              <div className="space-y-3">
                {topCountries.slice(0, 10).map((country, idx) => (
                  <div key={idx} className="flex items-center justify-between">
                    <span className="text-sm font-medium">{country.country || 'Unknown'}</span>
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
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Smartphone className="w-5 h-5" />
              Top Podcast Apps
            </CardTitle>
            <CardDescription>Where listeners are tuning in</CardDescription>
          </CardHeader>
          <CardContent>
            {topApps.length > 0 ? (
              <div className="space-y-3">
                {topApps.slice(0, 10).map((app, idx) => (
                  <div key={idx} className="flex items-center justify-between">
                    <span className="text-sm font-medium">{app.app || 'Unknown'}</span>
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

      {/* OP3 Attribution & Cache Notice */}
      <Card className="bg-gray-50 border-gray-200">
        <CardContent className="pt-6">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm text-gray-600">
              <div>
                <p className="font-medium">Analytics powered by OP3</p>
                <p className="text-xs mt-1">Open Podcast Prefix Project - Privacy-respecting podcast analytics</p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.open('https://op3.dev', '_blank')}
              >
                Learn More
              </Button>
            </div>
            <div className="border-t border-gray-200 pt-3 text-xs text-gray-500">
              <p>📊 Analytics data is cached and updates every <strong>3 hours</strong> to reduce API load.</p>
              <p className="mt-1">🔄 Refresh this page to check for new data if it's been more than 3 hours since your last visit.</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
