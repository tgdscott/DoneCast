import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function DashboardOverviewTab({ analytics, runSeed, seedResult }) {
  return (
    <div className="space-y-2">
      {analytics && (
        <div className="grid md:grid-cols-3 gap-6 mb-8">
          <Card>
            <CardContent className="p-4">
              <div className="text-sm text-gray-500">Users</div>
              <div className="text-2xl font-bold">{analytics.totalUsers}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-sm text-gray-500">Episodes</div>
              <div className="text-2xl font-bold">{analytics.totalEpisodes}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-sm text-gray-500">Published</div>
              <div className="text-2xl font-bold">{analytics.publishedEpisodes}</div>
            </CardContent>
          </Card>
        </div>
      )}
      <Button size="sm" variant="outline" onClick={runSeed}>
        Seed Demo Data
      </Button>
      {seedResult && (
        <div className="text-xs text-green-700 mt-2">
          Seeded podcast {seedResult.podcast_id.slice(0, 8)} / template {seedResult.template_id.slice(0, 8)}
        </div>
      )}
    </div>
  );
}
