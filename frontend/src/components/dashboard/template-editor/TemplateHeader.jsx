import { Button } from "@/components/ui/button";
import { ArrowLeft, Loader2, Save } from "lucide-react";

const TemplateHeader = ({ isDirty, isSaving, onBack, onSave }) => (
  <div className="flex justify-between items-center mb-6">
    <Button onClick={onBack} variant="ghost" className="text-gray-700">
      <ArrowLeft className="w-4 h-4 mr-2" />
      Back
    </Button>
    <h1 className="text-2xl font-bold text-gray-800">Template Editor</h1>
    <div className="flex items-center gap-3">
      {isDirty && !isSaving && (
        <span className="text-xs text-amber-600 font-medium">Unsaved changes</span>
      )}
      <Button
        onClick={onSave}
        disabled={isSaving}
        className="bg-blue-600 hover:bg-blue-700 text-white"
      >
        {isSaving ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Saving...
          </>
        ) : (
          <>
            <Save className="w-4 h-4 mr-2" />
            Save Template
          </>
        )}
      </Button>
    </div>
  </div>
);

export default TemplateHeader;
