import RecurringScheduleManager from "../../RecurringScheduleManager";
import TemplatePageWrapper from "../layout/TemplatePageWrapper";

const TemplateSchedulePage = ({ 
  token,
  templateId,
  userTimezone,
  isNewTemplate,
  onDirtyChange,
  onNext,
  onBack
}) => {
  return (
    <TemplatePageWrapper
      title="Publish Schedule"
      description="Set up automatic publishing on specific days and times (optional)"
      onNext={onNext}
      onBack={onBack}
      hasNext={true}
      hasPrevious={true}
    >
      <RecurringScheduleManager
        token={token}
        templateId={templateId}
        userTimezone={userTimezone}
        isNewTemplate={isNewTemplate}
        onDirtyChange={onDirtyChange}
        collapsible={false}
        defaultOpen={true}
      />
    </TemplatePageWrapper>
  );
};

export default TemplateSchedulePage;
