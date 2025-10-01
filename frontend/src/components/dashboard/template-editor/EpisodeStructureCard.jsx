import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DragDropContext, Draggable, Droppable } from "@hello-pangea/dnd";
import { ChevronDown } from "lucide-react";
import AddSegmentButton from "./AddSegmentButton";
import SegmentEditor from "./SegmentEditor";

const EpisodeStructureCard = ({
  isOpen,
  onToggle,
  segments,
  hasContentSegment,
  addSegment,
  onSourceChange,
  deleteSegment,
  introFiles,
  outroFiles,
  commercialFiles,
  onDragEnd,
  onOpenTTS,
  createdFromTTS,
  templateVoiceId,
  token,
  onMediaUploaded,
}) => (
  <Card className="shadow-sm" data-tour="template-structure">
    <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <CardTitle>Episode Structure</CardTitle>
        <CardDescription>
          Keep your bit segments aligned and drag to fine-tune the running order.
        </CardDescription>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="mt-2 h-8 px-2 text-slate-600 sm:mt-0"
        onClick={onToggle}
        aria-expanded={isOpen}
      >
        <ChevronDown className={`h-4 w-4 transition-transform ${isOpen ? "rotate-180" : ""}`} />
        <span className="sr-only">Toggle episode structure</span>
      </Button>
    </CardHeader>
    {isOpen && (
      <CardContent className="space-y-8">
        <div className="grid gap-6 lg:grid-cols-[minmax(220px,1fr)_minmax(320px,1.6fr)]">
          <section className="space-y-4" data-tour="template-add">
            <div className="space-y-1">
              <p className="text-xs uppercase tracking-wide text-slate-500">Bit segments</p>
              <h3 className="text-base font-semibold text-slate-800">Add segments</h3>
              <p className="text-sm text-slate-600">Drop in the recurring pieces that make up each episode.</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
              <AddSegmentButton type="intro" onClick={addSegment} />
              <AddSegmentButton type="content" onClick={addSegment} disabled={hasContentSegment} />
              <AddSegmentButton type="outro" onClick={addSegment} />
              <AddSegmentButton type="commercial" onClick={addSegment} />
            </div>
          </section>
          <section className="space-y-4">
            <div className="space-y-1">
              <p className="text-xs uppercase tracking-wide text-slate-500">Segment order</p>
              <h3 className="text-base font-semibold text-slate-800">Arrange your show flow</h3>
              <p className="text-sm text-slate-600">Drag and drop segments to update the running order.</p>
            </div>
            <DragDropContext onDragEnd={onDragEnd}>
              <Droppable droppableId="segments">
                {(provided) => (
                  <div {...provided.droppableProps} ref={provided.innerRef} className="space-y-3">
                    {segments.map((segment, index) => (
                      <Draggable
                        key={segment.id}
                        draggableId={segment.id}
                        index={index}
                        isDragDisabled={segment.segment_type === "content"}
                      >
                        {(dragProvided, snapshot) => (
                          <div
                            ref={dragProvided.innerRef}
                            {...dragProvided.draggableProps}
                            {...dragProvided.dragHandleProps}
                          >
                            <SegmentEditor
                              segment={segment}
                              onDelete={() => deleteSegment(segment.id)}
                              onSourceChange={onSourceChange}
                              mediaFiles={{ intro: introFiles, outro: outroFiles, commercial: commercialFiles }}
                              isDragging={snapshot.isDragging}
                              onOpenTTS={(prefill) => onOpenTTS(segment, prefill)}
                              justCreatedTs={createdFromTTS[segment.id] || null}
                              templateVoiceId={templateVoiceId}
                              token={token}
                              onMediaUploaded={onMediaUploaded}
                            />
                          </div>
                        )}
                      </Draggable>
                    ))}
                    {provided.placeholder}
                  </div>
                )}
              </Droppable>
            </DragDropContext>
          </section>
        </div>
      </CardContent>
    )}
  </Card>
);

export default EpisodeStructureCard;
