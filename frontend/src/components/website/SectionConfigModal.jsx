/**
 * Section Config Modal - Edit configuration for a specific section
 */

import { useState, useEffect } from "react";
import { X } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { getSectionIcon } from "./sections/SectionPreviews";

/**
 * Render a form field based on its type
 */
function ConfigField({ field, value, onChange }) {
  const handleChange = (newValue) => {
    onChange(field.name, newValue);
  };

  switch (field.type) {
    case "text":
      return (
        <Input
          placeholder={field.placeholder}
          value={value || field.default || ""}
          onChange={(e) => handleChange(e.target.value)}
        />
      );

    case "textarea":
      return (
        <Textarea
          placeholder={field.placeholder}
          value={value || field.default || ""}
          onChange={(e) => handleChange(e.target.value)}
          rows={4}
        />
      );

    case "url":
      return (
        <Input
          type="url"
          placeholder={field.placeholder}
          value={value || field.default || ""}
          onChange={(e) => handleChange(e.target.value)}
        />
      );

    case "number":
      return (
        <Input
          type="number"
          placeholder={field.placeholder}
          value={value ?? field.default ?? ""}
          onChange={(e) => handleChange(parseInt(e.target.value, 10))}
        />
      );

    case "color":
      return (
        <div className="flex gap-2">
          <Input
            type="color"
            value={value || field.default || "#000000"}
            onChange={(e) => handleChange(e.target.value)}
            className="w-20 h-10"
          />
          <Input
            type="text"
            value={value || field.default || "#000000"}
            onChange={(e) => handleChange(e.target.value)}
            placeholder="#000000"
            className="flex-1 font-mono"
          />
        </div>
      );

    case "toggle":
      return (
        <Switch
          checked={value ?? field.default ?? false}
          onCheckedChange={handleChange}
        />
      );

    case "select":
      return (
        <Select value={value || field.default} onValueChange={handleChange}>
          <SelectTrigger>
            <SelectValue placeholder={`Select ${field.label.toLowerCase()}`} />
          </SelectTrigger>
          <SelectContent>
            {field.options?.map((option) => (
              <SelectItem key={option} value={option}>
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );

    case "multiselect":
      // Simplified multiselect - store as array
      const selectedValues = value || field.default || [];
      return (
        <div className="space-y-2">
          {field.options?.map((option) => (
            <label key={option} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selectedValues.includes(option)}
                onChange={(e) => {
                  const newValues = e.target.checked
                    ? [...selectedValues, option]
                    : selectedValues.filter((v) => v !== option);
                  handleChange(newValues);
                }}
                className="rounded"
              />
              <span className="text-sm">{option}</span>
            </label>
          ))}
        </div>
      );

    case "image":
      return (
        <div className="space-y-2">
          <Input
            type="url"
            placeholder="Image URL"
            value={value || field.default || ""}
            onChange={(e) => handleChange(e.target.value)}
          />
          {value && (
            <img
              src={value}
              alt="Preview"
              className="max-w-xs rounded border border-slate-200"
            />
          )}
        </div>
      );

    default:
      return (
        <Input
          placeholder={field.placeholder}
          value={value || field.default || ""}
          onChange={(e) => handleChange(e.target.value)}
        />
      );
  }
}

/**
 * Main config modal component
 */
export default function SectionConfigModal({
  open,
  onClose,
  section,
  sectionDef,
  config,
  onSave,
}) {
  const [localConfig, setLocalConfig] = useState(config || {});

  useEffect(() => {
    if (open) {
      setLocalConfig(config || {});
    }
  }, [open, config]);

  const handleFieldChange = (fieldName, value) => {
    setLocalConfig((prev) => ({
      ...prev,
      [fieldName]: value,
    }));
  };

  const handleSave = () => {
    onSave(localConfig);
  };

  if (!sectionDef) return null;

  const Icon = getSectionIcon(sectionDef.icon);
  const allFields = [
    ...sectionDef.required_fields,
    ...sectionDef.optional_fields,
  ];

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="text-slate-400">{Icon}</div>
            <div>
              <DialogTitle>{sectionDef.label}</DialogTitle>
              <DialogDescription>{sectionDef.description}</DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Configuration fields */}
          {allFields.length > 0 ? (
            <div className="space-y-4">
              <div className="text-sm font-semibold text-slate-900">
                Configuration
              </div>
              {allFields.map((field) => (
                <div key={field.name} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor={field.name}>
                      {field.label}
                      {field.required && (
                        <span className="text-red-500 ml-1">*</span>
                      )}
                    </Label>
                    {field.help_text && (
                      <span className="text-xs text-slate-500">
                        {field.help_text}
                      </span>
                    )}
                  </div>
                  <ConfigField
                    field={field}
                    value={localConfig[field.name]}
                    onChange={handleFieldChange}
                  />
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-slate-500 text-center py-4">
              This section has no configuration options.
            </div>
          )}

        </div>

        {/* Footer actions */}
        <div className="flex justify-end gap-2 pt-4 border-t border-slate-200">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave}>
            Save Changes
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
