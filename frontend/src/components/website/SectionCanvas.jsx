/**
 * Section Canvas - Drag-and-drop area for website sections
 * Uses @dnd-kit for sortable functionality
 */

import { useState } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { 
  GripVertical, 
  Eye, 
  EyeOff, 
  Settings, 
  Trash2, 
  ChevronUp, 
  ChevronDown 
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { getSectionPreviewComponent, getSectionIcon } from "./sections/SectionPreviews";

/**
 * Individual sortable section item
 */
function SortableSection({
  section,
  sectionDef,
  config,
  enabled,
  onToggle,
  onEdit,
  onDelete,
  onMoveUp,
  onMoveDown,
  canMoveUp,
  canMoveDown,
  podcast,
  episodes,
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: section.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const PreviewComponent = getSectionPreviewComponent(section.id);
  const Icon = getSectionIcon(sectionDef?.icon);

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`
        group relative rounded-lg border-2 transition-all
        ${enabled ? "border-slate-200 bg-white" : "border-dashed border-slate-300 bg-slate-50"}
        ${isDragging ? "shadow-2xl z-50" : "hover:shadow-md"}
      `}
    >
      {/* Drag handle bar */}
      <div className="flex items-center justify-between gap-2 px-4 py-2 border-b border-slate-100">
        <div className="flex items-center gap-2">
          {/* Drag handle */}
          <button
            {...attributes}
            {...listeners}
            className="cursor-grab active:cursor-grabbing text-slate-400 hover:text-slate-600 touch-none"
            aria-label="Drag to reorder"
          >
            <GripVertical className="h-5 w-5" />
          </button>

          {/* Section info */}
          <div className="text-slate-400">{Icon}</div>
          <div>
            <div className="text-sm font-semibold text-slate-900">
              {sectionDef?.label || section.id}
            </div>
            <div className="text-xs text-slate-500">
              {sectionDef?.category}
            </div>
          </div>

          {sectionDef?.default_enabled && (
            <Badge variant="secondary" className="text-xs">
              Recommended
            </Badge>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1">
          {/* Move up/down buttons */}
          <Button
            size="sm"
            variant="ghost"
            onClick={onMoveUp}
            disabled={!canMoveUp}
            className="h-7 w-7 p-0"
            title="Move up"
          >
            <ChevronUp className="h-4 w-4" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onMoveDown}
            disabled={!canMoveDown}
            className="h-7 w-7 p-0"
            title="Move down"
          >
            <ChevronDown className="h-4 w-4" />
          </Button>

          {/* Toggle visibility */}
          <Button
            size="sm"
            variant="ghost"
            onClick={onToggle}
            className="h-7 w-7 p-0"
            title={enabled ? "Hide section" : "Show section"}
          >
            {enabled ? (
              <Eye className="h-4 w-4 text-slate-600" />
            ) : (
              <EyeOff className="h-4 w-4 text-slate-400" />
            )}
          </Button>

          {/* Edit config */}
          <Button
            size="sm"
            variant="ghost"
            onClick={onEdit}
            className="h-7 w-7 p-0"
            title="Configure section"
          >
            <Settings className="h-4 w-4 text-slate-600" />
          </Button>

          {/* Delete */}
          <Button
            size="sm"
            variant="ghost"
            onClick={onDelete}
            className="h-7 w-7 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
            title="Remove section"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Section preview */}
      <div className="p-4">
        <PreviewComponent
          sectionDef={sectionDef}
          config={config}
          enabled={enabled}
          podcast={podcast}
          episodes={episodes}
        />
      </div>

      {!enabled && (
        <div className="absolute inset-0 bg-slate-900/5 rounded-lg flex items-center justify-center pointer-events-none">
          <Badge variant="secondary">Hidden</Badge>
        </div>
      )}
    </div>
  );
}

/**
 * Main canvas component
 */
export default function SectionCanvas({
  sections = [],
  sectionsConfig = {},
  sectionsEnabled = {},
  availableSectionDefs = {},
  onReorder,
  onToggleSection,
  onEditSection,
  onDeleteSection,
  podcast = null,
  episodes = [],
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // Require 8px of movement before dragging starts
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  function handleDragEnd(event) {
    const { active, over } = event;

    if (active.id !== over?.id) {
      const oldIndex = sections.findIndex((s) => s.id === active.id);
      const newIndex = sections.findIndex((s) => s.id === over.id);

      const newOrder = arrayMove(sections, oldIndex, newIndex);
      onReorder(newOrder);
    }
  }

  function handleMoveUp(index) {
    if (index > 0) {
      const newOrder = arrayMove(sections, index, index - 1);
      onReorder(newOrder);
    }
  }

  function handleMoveDown(index) {
    if (index < sections.length - 1) {
      const newOrder = arrayMove(sections, index, index + 1);
      onReorder(newOrder);
    }
  }

  if (sections.length === 0) {
    return (
      <div className="rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 p-12 text-center">
        <div className="text-slate-400 mb-2">
          <GripVertical className="h-8 w-8 mx-auto" />
        </div>
        <h3 className="text-lg font-semibold text-slate-900 mb-1">
          No sections yet
        </h3>
        <p className="text-sm text-slate-600 max-w-md mx-auto">
          Add sections from the palette on the left to start building your website.
          You can drag to reorder, configure each section, and toggle visibility.
        </p>
      </div>
    );
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={handleDragEnd}
    >
      <SortableContext
        items={sections.map((s) => s.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="space-y-4">
          {sections.map((section, index) => {
            const sectionDef = availableSectionDefs[section.id];
            const config = sectionsConfig[section.id] || {};
            const enabled = sectionsEnabled[section.id] !== false; // Default to true

            return (
              <SortableSection
                key={section.id}
                section={section}
                sectionDef={sectionDef}
                config={config}
                enabled={enabled}
                onToggle={() => onToggleSection(section.id, !enabled)}
                onEdit={() => onEditSection(section.id)}
                onDelete={() => onDeleteSection(section.id)}
                onMoveUp={() => handleMoveUp(index)}
                onMoveDown={() => handleMoveDown(index)}
                canMoveUp={index > 0}
                canMoveDown={index < sections.length - 1}
                podcast={podcast}
                episodes={episodes}
              />
            );
          })}
        </div>
      </SortableContext>
    </DndContext>
  );
}
