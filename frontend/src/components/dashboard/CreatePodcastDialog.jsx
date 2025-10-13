import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Loader2 } from "lucide-react";
import { makeApi, isApiError } from "@/lib/apiClient";

export default function CreatePodcastDialog({ isOpen, onClose, onSave, token }) {
  const [formData, setFormData] = useState({
    name: "",
    description: "",
    cover_path: "",
    podcast_type: "episodic", // Default to episodic
    language: "en", // Default to English
    copyright_line: "",
    owner_name: "",
    author_name: "",
  });
  const [isSaving, setIsSaving] = useState(false);
  const { toast } = useToast();

  const handleChange = (e) => {
    const { id, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [id]: value,
    }));
  };

  const handleSelectChange = (id, value) => {
    setFormData((prev) => ({
      ...prev,
      [id]: value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    try {
  const api = makeApi(token);
  const newPodcast = await api.post(`/api/podcasts/`, formData);
      onSave(newPodcast); // Update state in parent component
      toast({ title: "Success", description: "Podcast created successfully." });
      onClose();
    } catch (error) {
  const msg = isApiError(error) ? (error.detail || error.error || error.message) : String(error);
  toast({ title: "Error", description: msg, variant: "destructive" });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Create New Podcast</DialogTitle>
          <DialogDescription>Enter the details for your new podcast.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="name" className="text-right">
                Name
              </Label>
              <Input id="name" value={formData.name} onChange={handleChange} className="col-span-3" required />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="description" className="text-right">
                Description
              </Label>
              <Textarea id="description" value={formData.description} onChange={handleChange} className="col-span-3" />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="cover_path" className="text-right">
                Cover Image URL
              </Label>
              <Input id="cover_path" value={formData.cover_path} onChange={handleChange} className="col-span-3" />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="podcast_type" className="text-right">
                Podcast Type
              </Label>
              <Select
                value={formData.podcast_type}
                onValueChange={(value) => handleSelectChange("podcast_type", value)}
              >
                <SelectTrigger className="col-span-3">
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="episodic">Episodic</SelectItem>
                  <SelectItem value="serial">Serial</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="language" className="text-right">
                Language
              </Label>
              <Input id="language" value={formData.language} onChange={handleChange} className="col-span-3" />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="copyright_line" className="text-right">
                Copyright Line
              </Label>
              <Input id="copyright_line" value={formData.copyright_line} onChange={handleChange} className="col-span-3" />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="owner_name" className="text-right">
                Owner Name
              </Label>
              <Input id="owner_name" value={formData.owner_name} onChange={handleChange} className="col-span-3" />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="author_name" className="text-right">
                Author Name
              </Label>
              <Input id="author_name" value={formData.author_name} onChange={handleChange} className="col-span-3" />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : ""}Create Podcast
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
