import { Card } from "@/components/ui/card";
import { Check, Circle } from "lucide-react";
import { Progress } from "@/components/ui/progress";

const OnboardingSidebar = ({ 
  steps = [],
  currentIndex = 0,
  completedSteps = new Set(),
  onStepClick,
  className = ""
}) => {
  const totalSteps = steps.length;
  // Include current step in count (step 1 = 1 completed, step 2 = 2 completed, etc.)
  const completedCount = completedSteps.size + (currentIndex >= 0 ? 1 : 0);
  const progress = totalSteps > 0 ? Math.round((completedCount / totalSteps) * 100) : 0;

  const getStepState = (stepIndex) => {
    if (stepIndex === currentIndex) return 'active';
    if (completedSteps.has(stepIndex)) return 'completed';
    return 'incomplete';
  };

  const StepIcon = ({ state, step, stepIndex }) => {
    if (state === 'completed') {
      return <Check className="w-5 h-5 text-green-600" />;
    }
    if (state === 'active') {
      // Use the step icon if available, otherwise use a numbered circle
      const StepIconComponent = step?.icon;
      if (StepIconComponent) {
        return <StepIconComponent className="w-5 h-5 text-blue-600" />;
      }
      return <div className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center text-white text-xs font-bold">{stepIndex + 1}</div>;
    }
    return <Circle className="w-5 h-5 text-gray-400" />;
  };

  const canNavigateToStep = (stepIndex) => {
    // Can navigate to current step or any completed step (steps we've moved past)
    // Cannot navigate forward to incomplete steps
    return stepIndex <= currentIndex;
  };

  return (
    <aside className={`space-y-4 ${className}`}>
      {/* Progress Card */}
      <Card className="p-4 bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
        <div className="flex items-center gap-2 mb-2">
          <h3 className="font-semibold text-blue-900">Setup Progress</h3>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-blue-700">Progress</span>
            <span className="font-semibold text-blue-900">{completedCount} of {totalSteps} steps</span>
          </div>
          <Progress value={progress} className="h-2" />
        </div>
      </Card>

      {/* Navigation */}
      <Card className="p-4">
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Steps
        </h4>
        <div className="space-y-1">
          {steps.map((step, index) => {
            const state = getStepState(index);
            const canNavigate = canNavigateToStep(index);
            
            return (
              <button
                key={step.id || index}
                onClick={() => canNavigate && onStepClick?.(index)}
                disabled={!canNavigate}
                className={`
                  w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-all
                  ${state === 'active' 
                    ? 'bg-blue-50 border-2 border-blue-500 text-blue-900 font-medium' 
                    : state === 'completed'
                    ? 'bg-green-50 hover:bg-green-100 text-green-900 cursor-pointer'
                    : 'hover:bg-gray-50 text-gray-600 cursor-not-allowed opacity-60'
                  }
                  ${!canNavigate ? 'pointer-events-none' : ''}
                `}
                title={!canNavigate ? 'Complete previous steps first' : step.title}
              >
                <StepIcon state={state} step={step} stepIndex={index} />
                <span className="text-sm flex-1 text-left">{step.title}</span>
              </button>
            );
          })}
        </div>
      </Card>
    </aside>
  );
};

export default OnboardingSidebar;

