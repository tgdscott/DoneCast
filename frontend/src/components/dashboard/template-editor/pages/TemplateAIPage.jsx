import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import TemplateAIContent from "../../TemplateAIContent";
import TemplatePageWrapper from "../layout/TemplatePageWrapper";

const TemplateAIPage = ({ aiSettings, defaultSettings, onChange, onNext, onBack }) => {
  return (
    <TemplatePageWrapper
      title="AI Content Guidance"
      description="Tell the AI how to write titles, show notes, and tags for your episodes (optional)"
      onNext={onNext}
      onBack={onBack}
      hasNext={true}
      hasPrevious={true}
    >
      <Card className="shadow-sm" data-tour="template-ai-guidance" data-tour-id="template-ai-content">
        <CardHeader>
          <CardTitle>AI Content Settings</CardTitle>
          <CardDescription>
            The AI can auto-generate episode titles, show notes, and tags based on your content. 
            Customize the style and tone here, or use the defaults.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <TemplateAIContent 
            value={aiSettings || defaultSettings} 
            onChange={onChange} 
            className="space-y-5" 
          />
        </CardContent>
      </Card>
    </TemplatePageWrapper>
  );
};

export default TemplateAIPage;
