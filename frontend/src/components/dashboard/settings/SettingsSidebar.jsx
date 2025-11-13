import { Card } from "@/components/ui/card";
import { User, Palette, Radio, AlertTriangle, Settings as SettingsIcon, Share2 } from "lucide-react";

const SECTIONS = [
  { id: 'profile', title: 'Profile', icon: User, required: true },
  { id: 'display', title: 'Display', icon: Palette, required: false },
  { id: 'audio', title: 'Audio', icon: Radio, required: false },
  { id: 'referral', title: 'Referral', icon: Share2, required: false },
  { id: 'account', title: 'Account', icon: AlertTriangle, required: false },
];

const SettingsSidebar = ({ 
  currentSection, 
  onSectionChange,
  className = ""
}) => {
  const getSectionState = (sectionId) => {
    if (sectionId === currentSection) return 'active';
    return 'incomplete';
  };

  const PageIcon = ({ state, Icon }) => {
    if (state === 'active') {
      return <Icon className="w-5 h-5 text-blue-600" />;
    }
    return <Icon className="w-5 h-5 text-gray-400" />;
  };

  return (
    <aside className={`w-64 space-y-4 flex-shrink-0 ${className}`}>
      {/* Info Card */}
      <Card className="p-4 bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
        <div className="flex items-center gap-2 mb-2">
          <SettingsIcon className="w-5 h-5 text-blue-600" />
          <h3 className="font-semibold text-blue-900">Settings</h3>
        </div>
        <p className="text-sm text-blue-700">
          Tune the workspace so it feels welcoming and make sure your automations know who they are helping.
        </p>
      </Card>

      {/* Navigation */}
      <Card className="p-4">
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Sections
        </h4>
        <div className="space-y-1">
          {SECTIONS.map((section) => {
            const state = getSectionState(section.id);
            const Icon = section.icon;
            return (
              <button
                key={section.id}
                onClick={() => onSectionChange(section.id)}
                className={`
                  w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-all
                  ${state === 'active' 
                    ? 'bg-blue-50 border-2 border-blue-500 text-blue-900 font-medium' 
                    : 'hover:bg-gray-50 text-gray-700'
                  }
                `}
              >
                <PageIcon state={state} Icon={Icon} />
                <span className="text-sm flex-1">{section.title}</span>
              </button>
            );
          })}
        </div>
      </Card>
    </aside>
  );
};

export default SettingsSidebar;
export { SECTIONS };

