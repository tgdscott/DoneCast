import { Button } from "@/components/ui/button";
import { ArrowLeft, ArrowRight, Info } from "lucide-react";

const TemplatePageWrapper = ({
  title,
  description,
  children,
  onBack,
  onNext,
  hasPrevious = true,
  hasNext = true,
  showWizardBanner = true,
}) => {
  return (
    <div className="space-y-6">
      {/* Wizard Context Banner */}
      {showWizardBanner && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex gap-3">
          <Info className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-blue-900 mb-1">
              ✨ Your template is ready!
            </p>
            <p className="text-sm text-blue-700">
              The onboarding wizard created this template with basic segments. 
              Everything here is easy to customize and change.
            </p>
          </div>
        </div>
      )}

      {/* Page Header */}
      <div className="space-y-2">
        <h2 className="text-2xl font-bold text-gray-900">{title}</h2>
        {description && (
          <p className="text-gray-600">{description}</p>
        )}
      </div>

      {/* Page Content */}
      <div>
        {children}
      </div>

      {/* Navigation Buttons */}
      <div className="flex items-center justify-between pt-6 border-t">
        <div>
          {hasPrevious && onBack && (
            <Button 
              variant="outline" 
              onClick={onBack}
              className="gap-2"
            >
              <ArrowLeft className="w-4 h-4" />
              Previous
            </Button>
          )}
        </div>
        <div>
          {hasNext && onNext && (
            <Button 
              onClick={onNext}
              className="gap-2"
            >
              Continue
              <ArrowRight className="w-4 h-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default TemplatePageWrapper;
