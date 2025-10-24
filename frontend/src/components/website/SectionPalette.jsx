/**
 * Section Palette - Displays available sections grouped by category
 * Users can add sections to their website from here
 */

import { useState, useEffect } from "react";
import { Plus, Loader2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { getSectionIcon } from "./sections/SectionPreviews";

const categoryLabels = {
  core: "Core Sections",
  content: "Content",
  marketing: "Marketing",
  community: "Community",
  advanced: "Advanced",
};

export default function SectionPalette({ 
  availableSections = [], 
  onAddSection,
  existingSectionIds = [],
  loading = false 
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");

  // Group sections by category
  const sectionsByCategory = availableSections.reduce((acc, section) => {
    if (!acc[section.category]) {
      acc[section.category] = [];
    }
    acc[section.category].push(section);
    return acc;
  }, {});

  // Filter sections based on search
  const filteredSections = availableSections.filter((section) => {
    const matchesSearch = searchQuery === "" ||
      section.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
      section.description.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesCategory = selectedCategory === "all" || section.category === selectedCategory;
    
    return matchesSearch && matchesCategory;
  });

  const categories = ["all", ...Object.keys(sectionsByCategory).sort()];

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Search and filter */}
      <div className="space-y-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            placeholder="Search sections..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* Category tabs */}
        <div className="flex gap-2 flex-wrap">
          {categories.map((cat) => (
            <Button
              key={cat}
              size="sm"
              variant={selectedCategory === cat ? "default" : "outline"}
              onClick={() => setSelectedCategory(cat)}
              className="text-xs"
            >
              {cat === "all" ? "All" : categoryLabels[cat] || cat}
            </Button>
          ))}
        </div>
      </div>

      {/* Section cards */}
      <div className="space-y-2 max-h-[600px] overflow-y-auto pr-2">
        {filteredSections.length === 0 ? (
          <div className="text-center py-8 text-sm text-slate-500">
            No sections found matching "{searchQuery}"
          </div>
        ) : (
          filteredSections.map((section) => {
            const isAdded = existingSectionIds.includes(section.id);
            const Icon = getSectionIcon(section.icon);
            
            return (
              <Card
                key={section.id}
                className={`transition-all ${
                  isAdded ? "opacity-50 bg-slate-50" : "hover:shadow-md cursor-pointer"
                }`}
              >
                <CardContent className="p-4">
                  <div className="flex items-start gap-3">
                    <div className="text-slate-400 mt-1">{Icon}</div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <h4 className="font-semibold text-sm text-slate-900">
                          {section.label}
                        </h4>
                        {section.default_enabled && (
                          <Badge variant="secondary" className="text-xs">
                            Recommended
                          </Badge>
                        )}
                      </div>
                      
                      <p className="text-xs text-slate-600 mb-2 line-clamp-2">
                        {section.description}
                      </p>
                      
                      <div className="flex items-center justify-between gap-2">
                        <Badge variant="outline" className="text-xs">
                          {categoryLabels[section.category] || section.category}
                        </Badge>
                        
                        <Button
                          size="sm"
                          variant={isAdded ? "ghost" : "default"}
                          onClick={() => !isAdded && onAddSection(section)}
                          disabled={isAdded}
                          className="h-7"
                        >
                          {isAdded ? (
                            <>Added</>
                          ) : (
                            <>
                              <Plus className="mr-1 h-3 w-3" />
                              Add
                            </>
                          )}
                        </Button>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>

      {/* Stats footer */}
      <div className="text-xs text-slate-500 text-center pt-2 border-t">
        {filteredSections.length} section{filteredSections.length !== 1 ? "s" : ""} available
        {existingSectionIds.length > 0 && ` • ${existingSectionIds.length} added to your site`}
      </div>
    </div>
  );
}
