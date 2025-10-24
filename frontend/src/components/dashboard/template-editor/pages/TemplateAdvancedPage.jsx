import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import TemplatePageWrapper from "../layout/TemplatePageWrapper";

const TemplateAdvancedPage = ({ 
  template, 
  onTemplateChange,
  voiceName,
  onChooseVoice,
  internVoiceDisplay,
  onChooseInternVoice,
  onNext, 
  onBack 
}) => {
  return (
    <TemplatePageWrapper
      title="Advanced Settings"
      description="Configure default voices and template status"
      onNext={null} // Last page, no next button
      onBack={onBack}
      hasNext={false}
      hasPrevious={true}
      showWizardBanner={false}
    >
      <div className="space-y-6">
        {/* Voice Settings */}
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle>Default Voices</CardTitle>
            <CardDescription>
              Set default AI voices for TTS segments in this template
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="text-sm font-medium text-gray-700 mb-2 block">
                ElevenLabs Voice (AI-generated segments)
              </label>
              <div className="flex items-center gap-2">
                <div className="flex-1 px-3 py-2 border rounded-md bg-gray-50 text-sm">
                  {voiceName || 'No voice selected'}
                </div>
                <Button variant="outline" onClick={onChooseVoice}>
                  Choose Voice
                </Button>
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 mb-2 block">
                Intern Voice (Spoken commands detection)
              </label>
              <div className="flex items-center gap-2">
                <div className="flex-1 px-3 py-2 border rounded-md bg-gray-50 text-sm">
                  {internVoiceDisplay || 'No voice selected'}
                </div>
                <Button variant="outline" onClick={onChooseInternVoice}>
                  Choose Voice
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Template Status */}
        <Card className="shadow-sm" data-tour="template-status">
          <CardHeader>
            <CardTitle>Template Status</CardTitle>
            <CardDescription>
              Control whether this template appears in the episode creator
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-gray-900">
                  Status: {template?.is_active !== false ? "Active" : "Inactive"}
                </p>
                <p className="text-sm text-gray-600 mt-1">
                  {template?.is_active !== false 
                    ? "This template is available when creating episodes"
                    : "This template is hidden from the episode creator"
                  }
                </p>
              </div>
              <Button 
                variant="outline" 
                onClick={() => onTemplateChange('is_active', !(template?.is_active !== false))}
              >
                {template?.is_active !== false ? "Disable" : "Enable"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </TemplatePageWrapper>
  );
};

export default TemplateAdvancedPage;
