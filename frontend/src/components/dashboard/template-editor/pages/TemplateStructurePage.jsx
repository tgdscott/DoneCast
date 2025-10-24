import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DragDropContext, Draggable, Droppable } from "@hello-pangea/dnd";
import AddSegmentButton from "../AddSegmentButton";
import SegmentEditor from "../SegmentEditor";
import TemplatePageWrapper from "../layout/TemplatePageWrapper";

const TemplateStructurePage = ({
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
  onNext,
  onBack,
}) => {
  return (
    <TemplatePageWrapper
      title="Episode Structure"
      description="Build your show flow with intro, content, and outro segments"
      onNext={onNext}
      onBack={onBack}
      hasNext={true}
      hasPrevious={true}
    >
      <Card className="shadow-sm" data-tour="template-structure">
        <CardHeader>
          <CardTitle>Segment Flow</CardTitle>
          <CardDescription>
            Your template already has basic segments. Add more, customize each one, or drag to reorder.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Add segment buttons */}
          <div className="flex gap-2 justify-start items-center pb-2 border-b" data-tour="template-add" data-tour-id="template-add-segments">
            <AddSegmentButton type="intro" onClick={addSegment} size="lg" />
            <AddSegmentButton type="content" onClick={addSegment} disabled={hasContentSegment} size="lg" />
            <AddSegmentButton type="outro" onClick={addSegment} size="lg" />
            <AddSegmentButton type="commercial" onClick={addSegment} size="lg" disabled />
          </div>

          {/* Segment list with drag-drop */}
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-800 mb-2">Current Segments</h3>
              <p className="text-xs text-slate-600 mb-4">
                Drag segments by the handle (⋮⋮) to reorder. Content segment stays fixed.
              </p>
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
          </div>
        </CardContent>
      </Card>
    </TemplatePageWrapper>
  );
};

export default TemplateStructurePage;
