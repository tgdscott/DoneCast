import React from 'react';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Users,
  TrendingUp,
  Play,
  CheckCircle,
  AlertTriangle,
  MessageSquare,
  Download,
  Settings as SettingsIcon,
} from "lucide-react";

export default function AdminDashboardTab({ 
  analytics, 
  episodesToday, 
  recentActivity, 
  systemHealth, 
  growthMetrics,
  handleKillQueue, 
  killingQueue 
}) {
  const num = (v) => (typeof v === 'number' && isFinite(v) ? v : 0);

  return (
    <div className="space-y-6">
      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card className="border-0 shadow-sm bg-white hover:shadow-md transition-all">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Active Users</p>
                <p className="text-2xl font-bold" style={{ color: "#2C3E50" }}>
                  {num(analytics.activeUsers).toLocaleString()}
                </p>
                {growthMetrics?.active_users_change != null && (
                  <div className={`flex items-center mt-1 text-sm ${growthMetrics.active_users_change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    <TrendingUp className="w-3 h-3 mr-1" />
                    {growthMetrics.active_users_change >= 0 ? '+' : ''}{growthMetrics.active_users_change.toFixed(1)}% vs last month
                  </div>
                )}
              </div>
              <div className="p-3 rounded-full bg-blue-100">
                <Users className="w-6 h-6 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-sm bg-white hover:shadow-md transition-all">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Monthly Revenue</p>
                <p className="text-2xl font-bold" style={{ color: "#2C3E50" }}>
                  {analytics.revenue != null ? (
                    <>${num(analytics.revenue).toLocaleString()}</>
                  ) : (
                    <Badge variant="secondary">—</Badge>
                  )}
                </p>
                {growthMetrics?.revenue_change != null && (
                  <div className={`flex items-center mt-1 text-sm ${growthMetrics.revenue_change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    <TrendingUp className="w-3 h-3 mr-1" />
                    {growthMetrics.revenue_change >= 0 ? '+' : ''}{growthMetrics.revenue_change.toFixed(1)}% vs last month
                  </div>
                )}
              </div>
              <div className="p-3 rounded-full bg-green-100">
                <TrendingUp className="w-6 h-6 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-sm bg-white hover:shadow-md transition-all">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Episodes Today</p>
                <p className="text-2xl font-bold" style={{ color: "#2C3E50" }}>
                  {episodesToday ? num(episodesToday.total) : '—'}
                </p>
                {episodesToday && (
                  <div className="flex items-center mt-1 text-sm text-blue-600">
                    <Play className="w-3 h-3 mr-1" />
                    {num(episodesToday.published)} published, {num(episodesToday.drafts)} drafts
                  </div>
                )}
              </div>
              <div className="p-3 rounded-full bg-purple-100">
                <Play className="w-6 h-6 text-purple-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-sm bg-white hover:shadow-md transition-all">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">System Health</p>
                <p className={`text-2xl font-bold ${systemHealth?.status === 'operational' ? 'text-green-600' : 'text-orange-600'}`}>
                  {systemHealth ? `${systemHealth.uptime_percentage.toFixed(1)}%` : '—'}
                </p>
                <div className={`flex items-center mt-1 text-sm ${systemHealth?.status === 'operational' ? 'text-green-600' : 'text-orange-600'}`}>
                  {systemHealth?.status === 'operational' ? (
                    <>
                      <CheckCircle className="w-3 h-3 mr-1" />
                      All systems operational
                    </>
                  ) : (
                    <>
                      <AlertTriangle className="w-3 h-3 mr-1" />
                      System degraded
                    </>
                  )}
                </div>
              </div>
              <div className="p-3 rounded-full bg-green-100">
                <CheckCircle className="w-6 h-6 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Activity and Quick Actions */}
      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card className="border-0 shadow-sm bg-white">
            <CardHeader>
              <CardTitle
                className="flex items-center justify-between"
                style={{ color: "#2C3E50" }}>
                Recent Platform Activity
                <Button variant="ghost" size="sm" className="text-blue-600">
                  View All
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {recentActivity && recentActivity.length > 0 ? (
                recentActivity.map((activity, index) => {
                  let icon, color, bg;
                  if (activity.type === 'user_signup') {
                    icon = Users;
                    color = "text-blue-600";
                    bg = "bg-blue-100";
                  } else if (activity.type === 'episode_published') {
                    icon = Play;
                    color = "text-purple-600";
                    bg = "bg-purple-100";
                  } else {
                    icon = MessageSquare;
                    color = "text-gray-600";
                    bg = "bg-gray-100";
                  }
                  
                  return (
                    <div
                      key={index}
                      className="flex items-start space-x-4 p-4 rounded-lg hover:bg-gray-50 transition-all">
                      <div className={`p-2 rounded-full ${bg}`}>
                        {React.createElement(icon, { className: `w-4 h-4 ${color}` })}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-gray-800">{activity.title}</p>
                        <p className="text-sm text-gray-600">{activity.description}</p>
                        <p className="text-xs text-gray-500 mt-1">{activity.time}</p>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <p>No recent activity</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          {/* Quick Actions */}
          <Card className="border-0 shadow-sm bg-white">
            <CardHeader>
              <CardTitle style={{ color: "#2C3E50" }}>Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button
                variant="destructive"
                className="w-full justify-start"
                onClick={handleKillQueue}
                disabled={killingQueue}>
                <AlertTriangle className="w-4 h-4 mr-3" />
                {killingQueue ? 'Killing Tasks…' : 'KILL Tasks Queue'}
              </Button>
              <Button variant="outline" className="w-full justify-start bg-transparent">
                <MessageSquare className="w-4 h-4 mr-3" />
                Send Platform Announcement
              </Button>
              <Button variant="outline" className="w-full justify-start bg-transparent">
                <Download className="w-4 h-4 mr-3" />
                Generate Monthly Report
              </Button>
              <Button variant="outline" className="w-full justify-start bg-transparent">
                <SettingsIcon className="w-4 h-4 mr-3" />
                System Maintenance
              </Button>
              <Button variant="outline" className="w-full justify-start bg-transparent">
                <Users className="w-4 h-4 mr-3" />
                User Support Queue
              </Button>
            </CardContent>
          </Card>

          {/* System Status */}
          <Card className="border-0 shadow-sm" style={{ backgroundColor: "#ECF0F1" }}>
            <CardHeader>
              <CardTitle style={{ color: "#2C3E50" }}>System Status</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {[
                { service: "API Gateway", status: systemHealth?.status || "operational" },
                { service: "Database", status: systemHealth?.status || "operational" },
                { service: "AI Services", status: systemHealth?.status || "operational" },
                { service: "File Storage", status: systemHealth?.status || "operational" },
                { service: "Email Service", status: systemHealth?.status || "operational" },
              ].map((item, index) => {
                const isOperational = item.status === "operational";
                const icon = isOperational ? CheckCircle : AlertTriangle;
                const color = isOperational ? "text-green-600" : "text-orange-600";
                
                return (
                  <div key={index} className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      {React.createElement(icon, { className: `w-4 h-4 ${color}` })}
                      <span className="text-sm font-medium text-gray-700">{item.service}</span>
                    </div>
                    <Badge
                      className={`text-xs ${
                        isOperational
                          ? "bg-green-100 text-green-800"
                          : "bg-orange-100 text-orange-800"
                      }`}>
                      {item.status}
                    </Badge>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
