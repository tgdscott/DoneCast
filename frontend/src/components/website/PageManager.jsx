/**
 * Page Manager Component
 * UI for creating and managing website pages
 */

import { useState } from "react";
import { Plus, Edit2, Trash2, Home, GripVertical } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useWebsitePages } from "@/hooks/useWebsitePages";

export default function PageManager({ token, podcastId, website }) {
  const { pages, loading, createPage, updatePage, deletePage, loadPages } = useWebsitePages(token, podcastId);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [editingPage, setEditingPage] = useState(null);
  const [pageTitle, setPageTitle] = useState("");
  const [pageSlug, setPageSlug] = useState("");
  const [isHome, setIsHome] = useState(false);

  // Auto-generate slug from title
  const handleTitleChange = (title) => {
    setPageTitle(title);
    if (!editingPage) {
      // Auto-generate slug from title
      const slug = title
        .toLowerCase()
        .trim()
        .replace(/[^\w\s-]/g, '')
        .replace(/[-\s]+/g, '-')
        .substring(0, 200);
      setPageSlug(slug);
    }
  };

  const handleCreate = async () => {
    if (!pageTitle.trim()) return;
    try {
      await createPage(pageTitle.trim(), pageSlug.trim() || undefined, isHome);
      setShowCreateDialog(false);
      setPageTitle("");
      setPageSlug("");
      setIsHome(false);
    } catch (err) {
      // Error handled in hook
    }
  };

  const handleEdit = (page) => {
    setEditingPage(page);
    setPageTitle(page.title);
    setPageSlug(page.slug);
    setIsHome(page.is_home);
  };

  const handleUpdate = async () => {
    if (!editingPage || !pageTitle.trim()) return;
    try {
      await updatePage(editingPage.id, {
        title: pageTitle.trim(),
        slug: pageSlug.trim() || undefined,
        is_home: isHome,
      });
      setEditingPage(null);
      setPageTitle("");
      setPageSlug("");
      setIsHome(false);
    } catch (err) {
      // Error handled in hook
    }
  };

  const handleDelete = async (page) => {
    if (!confirm(`Delete "${page.title}"? This cannot be undone.`)) return;
    try {
      await deletePage(page.id);
    } catch (err) {
      // Error handled in hook
    }
  };

  if (!website) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg">Pages</CardTitle>
            <p className="text-xs text-slate-500 mt-1">
              Create multiple pages for your website. Navigation auto-populates from pages.
            </p>
          </div>
          <Button
            size="sm"
            onClick={() => {
              setEditingPage(null);
              setPageTitle("");
              setPageSlug("");
              setIsHome(false);
              setShowCreateDialog(true);
            }}
            disabled={loading}
          >
            <Plus className="mr-2 h-4 w-4" />
            New Page
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {pages.length === 0 ? (
          <div className="text-center py-8 text-sm text-slate-500">
            <p>No pages yet. Create your first page to get started!</p>
            <p className="text-xs mt-2">Single-page sites work great too - pages are optional.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {pages
              .sort((a, b) => a.order - b.order)
              .map((page) => (
                <div
                  key={page.id}
                  className="flex items-center justify-between p-3 border border-slate-200 rounded-lg hover:bg-slate-50"
                >
                  <div className="flex items-center gap-3 flex-1">
                    <GripVertical className="h-4 w-4 text-slate-400" />
                    {page.is_home && <Home className="h-4 w-4 text-purple-600" title="Home page" />}
                    <div className="flex-1">
                      <div className="font-medium text-slate-900">{page.title}</div>
                      <div className="text-xs text-slate-500">/{page.slug}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleEdit(page)}
                      className="h-8"
                    >
                      <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(page)}
                      disabled={page.is_home}
                      className="h-8 text-red-600 hover:text-red-700"
                      title={page.is_home ? "Cannot delete home page" : "Delete page"}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
          </div>
        )}
      </CardContent>

      {/* Create/Edit Dialog */}
      <Dialog open={showCreateDialog || !!editingPage} onOpenChange={(open) => {
        if (!open) {
          setShowCreateDialog(false);
          setEditingPage(null);
          setPageTitle("");
          setPageSlug("");
          setIsHome(false);
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingPage ? "Edit Page" : "Create New Page"}</DialogTitle>
            <DialogDescription>
              {editingPage 
                ? "Update page details. Changes will appear in navigation."
                : "Add a new page to your website. Each page can have its own sections."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="page-title">Page Title</Label>
              <Input
                id="page-title"
                placeholder="About Us"
                value={pageTitle}
                onChange={(e) => handleTitleChange(e.target.value)}
              />
              <p className="text-xs text-slate-500">This appears in navigation</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="page-slug">URL Slug</Label>
              <Input
                id="page-slug"
                placeholder="about-us"
                value={pageSlug}
                onChange={(e) => setPageSlug(e.target.value)}
              />
              <p className="text-xs text-slate-500">URL-friendly identifier (auto-generated from title)</p>
            </div>
            <div className="flex items-center space-x-2">
              <Switch
                id="is-home"
                checked={isHome}
                onCheckedChange={setIsHome}
              />
              <Label htmlFor="is-home" className="cursor-pointer">
                Set as home page
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setShowCreateDialog(false);
              setEditingPage(null);
              setPageTitle("");
              setPageSlug("");
              setIsHome(false);
            }}>
              Cancel
            </Button>
            <Button onClick={editingPage ? handleUpdate : handleCreate} disabled={!pageTitle.trim()}>
              {editingPage ? "Save Changes" : "Create Page"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}




