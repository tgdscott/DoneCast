import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Check, Circle, Compass } from "lucide-react";

const PAGES = [
  { id: 'basics', title: 'Name & Show', icon: '📋', required: true, group: 'required' },
  { id: 'schedule', title: 'Publish Schedule', icon: '📅', required: false, group: 'optional' },
  { id: 'ai', title: 'AI Guidance', icon: '🤖', required: false, group: 'optional' },
  { id: 'structure', title: 'Episode Structure', icon: '🎭', required: true, group: 'required' },
  { id: 'music', title: 'Music & Timing', icon: '🎵', required: false, group: 'optional' },
  { id: 'advanced', title: 'Advanced', icon: '⚙️', required: false, group: 'optional' },
];

const TemplateEditorSidebar = ({ 
  currentPage, 
  completedPages = new Set(), 
  onPageChange,
  className = ""
}) => {
  const requiredPages = PAGES.filter(p => p.required);
  const completedRequired = requiredPages.filter(p => completedPages.has(p.id)).length;
  const totalRequired = requiredPages.length;
  const progress = Math.round((completedRequired / totalRequired) * 100);

  const getPageState = (pageId) => {
    if (pageId === currentPage) return 'active';
    if (completedPages.has(pageId)) return 'completed';
    return 'incomplete';
  };

  const PageIcon = ({ state, icon }) => {
    if (state === 'completed') {
      return <Check className="w-5 h-5 text-green-600" />;
    }
    if (state === 'active') {
      return <div className="w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center text-white text-xs font-bold">{icon}</div>;
    }
    return <Circle className="w-5 h-5 text-gray-400" />;
  };

  return (
    <aside className={`space-y-4 ${className}`} data-tour="sidebar-nav">
      {/* Progress Card */}
      <Card className="p-4 bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
        <div className="flex items-center gap-2 mb-2">
          <Compass className="w-5 h-5 text-blue-600" />
          <h3 className="font-semibold text-blue-900">Template Setup</h3>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-blue-700">Progress</span>
            <span className="font-semibold text-blue-900">{completedRequired} of {totalRequired} required</span>
          </div>
          <div className="w-full bg-blue-200 rounded-full h-2" data-tour="progress">
            <div 
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </Card>

      {/* Navigation */}
      <Card className="p-4">
        {/* Required Section */}
        <div className="mb-4">
          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Required
          </h4>
          <div className="space-y-1">
            {PAGES.filter(p => p.required).map((page) => {
              const state = getPageState(page.id);
              return (
                <button
                  key={page.id}
                  onClick={() => onPageChange(page.id)}
                  className={`
                    w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-all
                    ${state === 'active' 
                      ? 'bg-blue-50 border-2 border-blue-500 text-blue-900 font-medium' 
                      : state === 'completed'
                      ? 'bg-green-50 hover:bg-green-100 text-green-900'
                      : 'hover:bg-gray-50 text-gray-700'
                    }
                  `}
                  data-tour-id={`nav-${page.id}`}
                >
                  <PageIcon state={state} icon={page.icon} />
                  <span className="text-sm flex-1">{page.title}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Optional Section */}
        <div>
          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Optional
          </h4>
          <div className="space-y-1">
            {PAGES.filter(p => !p.required).map((page) => {
              const state = getPageState(page.id);
              return (
                <button
                  key={page.id}
                  onClick={() => onPageChange(page.id)}
                  className={`
                    w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-all
                    ${state === 'active' 
                      ? 'bg-blue-50 border-2 border-blue-500 text-blue-900 font-medium' 
                      : state === 'completed'
                      ? 'bg-green-50 hover:bg-green-100 text-green-900'
                      : 'hover:bg-gray-50 text-gray-600'
                    }
                  `}
                  data-tour-id={`nav-${page.id}`}
                >
                  <PageIcon state={state} icon={page.icon} />
                  <span className="text-sm flex-1">{page.title}</span>
                </button>
              );
            })}
          </div>
        </div>
      </Card>
    </aside>
  );
};

export default TemplateEditorSidebar;
export { PAGES };
