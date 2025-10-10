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
      
      // Fetch show-level stats
      const showData = await api.get(`/api/analytics/podcast/${podcastId}/downloads?days=${timeRange}`);
      setShowStats(showData);
      
      // Fetch episode-level summary
      const episodesData = await api.get(`/api/analytics/podcast/${podcastId}/episodes-summary?limit=10`);
      setEpisodesStats(episodesData.episodes || []);
      
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
        <Card>
          <CardHeader>
            <CardTitle>Analytics Error</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-red-600 mb-4">{error}</div>
            <div className="space-y-2 text-sm text-gray-600">
              <p><strong>Note:</strong> Analytics data comes from OP3 (Open Podcast Prefix Project).</p>
              <p>If you're not seeing data, make sure:</p>
              <ul className="list-disc list-inside ml-4">
                <li>Your RSS feed has been deployed with OP3 prefixes</li>
                <li>Podcast apps are downloading episodes (data appears after first downloads)</li>
                <li>You've waited at least 24 hours after deployment</li>
              </ul>
              <Button onClick={fetchAnalytics} className="mt-4">Retry</Button>
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

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">{showStats?.podcast_name || 'Podcast Analytics'}</h1>
          <p className="text-gray-600 mt-1">Download statistics powered by OP3</p>
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
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
              <Download className="w-4 h-4" />
              Total Downloads
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{totalDownloads.toLocaleString()}</div>
            <p className="text-xs text-gray-500 mt-1">Last {timeRange} days</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
              <Globe className="w-4 h-4" />
              Countries
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{topCountries.length}</div>
            <p className="text-xs text-gray-500 mt-1">Geographic reach</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
              <Smartphone className="w-4 h-4" />
              Podcast Apps
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{topApps.length}</div>
            <p className="text-xs text-gray-500 mt-1">Different apps</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600 flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              Average/Day
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {downloadsData.length > 0
                ? Math.round(totalDownloads / downloadsData.length).toLocaleString()
                : '0'}
            </div>
            <p className="text-xs text-gray-500 mt-1">Daily average</p>
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
              <div className="text-center text-gray-500 py-8">No geographic data available</div>
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

      {/* Top Episodes */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5" />
            Top Episodes
          </CardTitle>
          <CardDescription>Most downloaded episodes in the last 30 days</CardDescription>
        </CardHeader>
        <CardContent>
          {episodesStats.length > 0 ? (
            <div className="space-y-2">
              {episodesStats.map((episode, idx) => (
                <div key={episode.episode_id} className="flex items-center justify-between p-3 border rounded-lg hover:bg-gray-50">
                  <div className="flex-1">
                    <div className="font-medium text-sm">
                      {episode.episode_number && `Episode ${episode.episode_number}: `}
                      {episode.title}
                    </div>
                    <div className="text-xs text-gray-500 mt-1 flex gap-4">
                      <span>24h: {episode.downloads_24h}</span>
                      <span>7d: {episode.downloads_7d}</span>
                      <span>30d: {episode.downloads_30d}</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold">{episode.downloads_total.toLocaleString()}</div>
                    <div className="text-xs text-gray-500">total</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center text-gray-500 py-8">No episode data available</div>
          )}
        </CardContent>
      </Card>

      {/* OP3 Attribution */}
      <Card className="bg-gray-50">
        <CardContent className="pt-6">
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
        </CardContent>
      </Card>
    </div>
  );
}
