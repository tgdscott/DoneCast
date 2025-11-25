import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Plus, Edit, Trash2, Loader2, ArrowLeft, Bot, FileText, Copy } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { useState, useEffect } from "react";
import TemplateEditor from "./TemplateEditor"; // We will use the editor as a sub-component
import { makeApi } from "@/lib/apiClient";

export default function TemplateManager({ onBack, token, setCurrentView }) {
  const [templates, setTemplates] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editingTemplateId, setEditingTemplateId] = useState(null); // This will control which view is shown

  const fetchTemplates = async () => {
    setIsLoading(true);
    setEditingTemplateId(null); // Always return to list view after a fetch
    try {
  const api = makeApi(token);
  const data = await api.get('/api/templates/');
      setTemplates(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTemplates();
  }, [token]);

  const handleCreateNew = () => {
    setEditingTemplateId('new'); // Use 'new' as a special ID for creation
  };

  const handleDelete = async (templateId) => {
    if (!window.confirm("Are you sure you want to delete this template?")) return;
    try {
  const api = makeApi(token);
  await api.del(`/api/templates/${templateId}`);
        // Refresh the list after deleting
        fetchTemplates();
    } catch (err) {
        // Special-case: last template safeguard
        const msg = (err && err.message) || '';
        if (msg.toLowerCase().includes('at least one template')){
          setError(null);
          alert('You need to create another template before deleting your last one.');
        } else {
          setError(msg || 'Delete failed');
        }
    }
  };

  const toggleActive = async (tpl) => {
    try {
      const api = makeApi(token);
      const next = { ...tpl, is_active: !(tpl?.is_active !== false) };
      await api.put(`/api/templates/${tpl.id}`, next);
      fetchTemplates();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDuplicate = async (templateId) => {
    try {
      const api = makeApi(token);
      await api.post(`/api/templates/${templateId}/duplicate`);
      fetchTemplates();
    } catch (err) {
      const msg = (err && err.message) || 'Duplicate failed';
      setError(msg);
    }
  };

  // If we are editing or creating, show the editor component
  if (editingTemplateId) {
    return (
      <TemplateEditor
        templateId={editingTemplateId}
        onBack={() => setEditingTemplateId(null)} // Go back to the manager list
        token={token}
        onTemplateSaved={fetchTemplates} // Refresh the list after saving
      />
    );
  }

  // Otherwise, show the list of templates
  return (
    <div className="p-6">
       <Button onClick={onBack} variant="ghost" className="mb-4"><ArrowLeft className="w-4 h-4 mr-2" />Back to Dashboard</Button>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">Template Manager</h1>
        <div className="flex gap-2 items-end">
          <div className="flex flex-col items-end">
            <span className="italic text-xs text-muted-foreground mb-1">Coming soon</span>
            <Button
              type="button"
              variant="outline"
              disabled
              className="opacity-60 cursor-not-allowed"
              title="AI Template Wizard is coming soon"
            >
              <Bot className="w-4 h-4 mr-2" />Create with AI Wizard
            </Button>
          </div>
          <Button onClick={handleCreateNew}><Plus className="w-4 h-4 mr-2" />Create New Template</Button>
        </div>
      </div>
      {isLoading && <div className="flex justify-center"><Loader2 className="w-8 h-8 animate-spin" /></div>}
      {error && <p className="text-red-500">{error}</p>}
      {!isLoading && !error && (
        <Card>
          <CardHeader>
            <CardTitle>Your Templates</CardTitle>
            <CardDescription>Select a template to edit or create a new one.</CardDescription>
          </CardHeader>
          <CardContent>
            {templates.length > 0 ? (
              <div className="space-y-2">
                {templates.map(template => (
                  <div key={template.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-md">
                    <div className="flex items-center gap-3">
                      <span className="font-semibold">{template.name}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${template?.is_active !== false ? 'bg-green-50 text-green-700 border-green-200' : 'bg-gray-100 text-gray-700 border-gray-300'}`}>
                        {template?.is_active !== false ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <div className="space-x-2">
                       <Button variant="outline" size="sm" onClick={() => toggleActive(template)}>{template?.is_active !== false ? 'Disable' : 'Enable'}</Button>
                       <Button variant="outline" size="sm" onClick={() => handleDuplicate(template.id)}><Copy className="w-4 h-4 mr-2"/>Duplicate</Button>
                       <Button variant="outline" size="sm" onClick={() => setEditingTemplateId(template.id)}><Edit className="w-4 h-4 mr-2"/>Edit</Button>
                       <Button variant="destructive" size="sm" onClick={() => handleDelete(template.id)}><Trash2 className="w-4 h-4 mr-2"/>Delete</Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No Templates Yet"
                description="Templates define the structure of your episodes. Create your first template to get started with episode creation."
                icon={FileText}
                action={{
                  label: "Create Your First Template",
                  onClick: handleCreateNew,
                  variant: "default",
                  icon: Plus
                }}
              />
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}