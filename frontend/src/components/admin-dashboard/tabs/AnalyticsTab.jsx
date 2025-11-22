import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TrendingUp, Users, Calendar, Play, Download } from "lucide-react";

const safeNumber = (value) => (typeof value === "number" && isFinite(value) ? value : 0);

export default function AnalyticsTab({ analytics, metrics, growthMetrics, systemHealth, analyticsLoading }) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold" style={{ color: "#2C3E50" }}>
            Platform Analytics
          </h3>
          <p className="text-gray-600">Comprehensive insights into platform performance</p>
        </div>
        <Select defaultValue="30d">
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7d">Last 7 days</SelectItem>
            <SelectItem value="30d">Last 30 days</SelectItem>
            <SelectItem value="90d">Last 90 days</SelectItem>
            <SelectItem value="1y">Last year</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {!analyticsLoading ? (
          <>
            <Card className="border-0 shadow-sm hover:shadow-md transition-all" style={{ backgroundColor: "#ECF0F1" }}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">Total Active Users</p>
                    <p className="text-3xl font-bold" style={{ color: "#2C3E50" }}>
                      {safeNumber(analytics.activeUsers).toLocaleString()}
                    </p>
                    {growthMetrics?.active_users_change != null && (
                      <div className={`flex items-center mt-2 text-sm ${growthMetrics.active_users_change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        <TrendingUp className="w-4 h-4 mr-1" />
                        <span>{growthMetrics.active_users_change >= 0 ? '+' : ''}{growthMetrics.active_users_change.toFixed(1)}% from last month</span>
                      </div>
                    )}
                  </div>
                  <div className="p-3 rounded-full bg-blue-100">
                    <Users className="w-8 h-8 text-blue-600" />
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <div className="text-xs text-gray-600">Latest daily active users (DAU) over last 30 days</div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-sm hover:shadow-md transition-all" style={{ backgroundColor: "#ECF0F1" }}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">New Sign-ups (30 Days)</p>
                    <p className="text-3xl font-bold" style={{ color: "#2C3E50" }}>
                      {safeNumber(analytics.newSignups).toLocaleString()}
                    </p>
                    {growthMetrics?.signups_change != null && (
                      <div className={`flex items-center mt-2 text-sm ${growthMetrics.signups_change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        <TrendingUp className="w-4 h-4 mr-1" />
                        <span>{growthMetrics.signups_change >= 0 ? '+' : ''}{growthMetrics.signups_change.toFixed(1)}% from last month</span>
                      </div>
                    )}
                  </div>
                  <div className="p-3 rounded-full bg-green-100">
                    <Calendar className="w-8 h-8 text-green-600" />
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <div className="text-xs text-gray-600">Daily average: {Math.round(safeNumber(analytics.newSignups) / 30)} users</div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-sm hover:shadow-md transition-all" style={{ backgroundColor: "#ECF0F1" }}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">Total Episodes Published</p>
                    <p className="text-3xl font-bold" style={{ color: "#2C3E50" }}>
                      {safeNumber(analytics.totalEpisodes).toLocaleString()}
                    </p>
                    {growthMetrics?.episodes_change != null && (
                      <div className={`flex items-center mt-2 text-sm ${growthMetrics.episodes_change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        <TrendingUp className="w-4 h-4 mr-1" />
                        <span>{growthMetrics.episodes_change >= 0 ? '+' : ''}{growthMetrics.episodes_change.toFixed(1)}% from last month</span>
                      </div>
                    )}
                  </div>
                  <div className="p-3 rounded-full bg-purple-100">
                    <Play className="w-8 h-8 text-purple-600" />
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <div className="text-xs text-gray-600">
                    Published: {safeNumber(analytics.publishedEpisodes).toLocaleString()} total
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-sm hover:shadow-md transition-all" style={{ backgroundColor: "#ECF0F1" }}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">Revenue (MRR)</p>
                    <p className="text-3xl font-bold" style={{ color: "#2C3E50" }}>
                      {analytics.revenue != null ? (
                        <>${Number(analytics.revenue).toLocaleString()}</>
                      ) : (
                        <Badge variant="secondary">—</Badge>
                      )}
                    </p>
                    {growthMetrics?.revenue_change != null && (
                      <div className={`flex items-center mt-2 text-sm ${growthMetrics.revenue_change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        <TrendingUp className="w-4 h-4 mr-1" />
                        <span>{growthMetrics.revenue_change >= 0 ? '+' : ''}{growthMetrics.revenue_change.toFixed(1)}% from last month</span>
                      </div>
                    )}
                  </div>
                  <div className="p-3 rounded-full bg-green-100">
                    <TrendingUp className="w-8 h-8 text-green-600" />
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <div className="text-xs text-gray-600">
                    ARPU: {analytics.revenue != null && analytics.totalUsers > 0 ? (
                      <>${(Number(analytics.revenue) / Number(analytics.totalUsers)).toFixed(2)}</>
                    ) : (
                      <Badge variant="secondary">—</Badge>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </>
        ) : (
          <>
            {Array.from({ length: 4 }).map((_, index) => (
              <Card key={index} className="border-0 shadow-sm">
                <CardContent className="p-6">
                  <div className="h-20 bg-gray-100 rounded animate-pulse" />
                </CardContent>
              </Card>
            ))}
          </>
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {!analyticsLoading ? (
          <>
            <Card className="border-0 shadow-sm bg-white">
              <CardHeader>
                <CardTitle className="flex items-center justify-between" style={{ color: "#2C3E50" }}>
                  Daily Signups (30 days)
                  <Button variant="ghost" size="sm" className="text-blue-600">
                    <Download className="w-4 h-4 mr-1" />
                    Export
                  </Button>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-64 flex items-end justify-between space-x-1 p-4 bg-gray-50 rounded-lg">
                  {(metrics?.daily_signups_30d || []).map((entry, index, arr) => {
                    const max = Math.max(1, ...arr.map((item) => Number(item.count) || 0));
                    const height = Math.round(((Number(entry.count) || 0) / max) * 200);
                    return (
                      <div key={index} className="flex flex-col items-center">
                        <div className="w-3 bg-blue-500 rounded-t" style={{ height: `${height}px` }} />
                        <span className="text-[10px] text-gray-500 mt-1">{String(entry.date).slice(5)}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="mt-4 flex items-center justify-between text-sm text-gray-600">
                  <span>Total signups: {safeNumber(analytics.newSignups).toLocaleString()}</span>
                  <span className="text-green-600">30 days</span>
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-sm bg-white">
              <CardHeader>
                <CardTitle className="flex items-center justify-between" style={{ color: "#2C3E50" }}>
                  Daily Active Users (30 days)
                  <Button variant="ghost" size="sm" className="text-blue-600">
                    <Download className="w-4 h-4 mr-1" />
                    Export
                  </Button>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-64 flex items-end justify-between space-x-1 p-4 bg-gray-50 rounded-lg">
                  {(metrics?.daily_active_users_30d || []).map((entry, index, arr) => {
                    const max = Math.max(1, ...arr.map((item) => Number(item.count) || 0));
                    const height = Math.round(((Number(entry.count) || 0) / max) * 200);
                    return (
                      <div key={index} className="flex flex-col items-center">
                        <div className="w-3 bg-purple-500 rounded-t" style={{ height: `${height}px` }} />
                        <span className="text-[10px] text-gray-500 mt-1">{String(entry.date).slice(5)}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="mt-4 flex items-center justify-between text-sm text-gray-600">
                  <span>Latest DAU: {safeNumber(analytics.activeUsers).toLocaleString()}</span>
                  <span className="text-green-600">30 days</span>
                </div>
              </CardContent>
            </Card>
          </>
        ) : (
          <>
            {Array.from({ length: 2 }).map((_, index) => (
              <Card key={index} className="border-0 shadow-sm bg-white">
                <CardContent className="p-6">
                  <div className="h-64 bg-gray-100 rounded animate-pulse" />
                </CardContent>
              </Card>
            ))}
          </>
        )}
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="border-0 shadow-sm bg-white">
          <CardHeader>
            <CardTitle style={{ color: "#2C3E50" }}>Top Performing Content</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-center py-8 text-gray-500">
              <p>Top performing content metrics coming soon</p>
              <p className="text-xs mt-2">This will show podcasts with highest download counts</p>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-sm bg-white">
          <CardHeader>
            <CardTitle style={{ color: "#2C3E50" }}>User Engagement</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-center py-8 text-gray-500">
              <p>User engagement metrics coming soon</p>
              <p className="text-xs mt-2">This will show retention and engagement statistics</p>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-sm bg-white">
          <CardHeader>
            <CardTitle style={{ color: "#2C3E50" }}>Platform Health</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-center">
              <div className={`text-3xl font-bold mb-2 ${systemHealth?.status === 'operational' ? 'text-green-600' : 'text-orange-600'}`}>
                {systemHealth ? `${systemHealth.uptime_percentage.toFixed(1)}%` : '—'}
              </div>
              <p className="text-sm text-gray-600">Uptime (30 days)</p>
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span>System Status</span>
                <span className={`font-medium ${systemHealth?.status === 'operational' ? 'text-green-600' : 'text-orange-600'}`}>
                  {systemHealth?.status || 'Unknown'}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Success Rate</span>
                <span className="font-medium text-green-600">
                  {systemHealth ? `${systemHealth.uptime_percentage.toFixed(1)}%` : '—'}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
