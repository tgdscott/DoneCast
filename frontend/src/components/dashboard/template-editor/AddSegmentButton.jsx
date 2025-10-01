import { Button } from "@/components/ui/button";
import { segmentIcons, segmentIconColors } from "./constants";

const AddSegmentButton = ({ type, onClick, disabled, size }) => {
  const Icon = segmentIcons[type];
  const colorClass = segmentIconColors[type] || "";
  // Slightly larger size for all buttons
  const btnSize = size === 'lg' ? 'h-24 w-24' : 'h-16 w-16';
  const iconSize = size === 'lg' ? 'w-7 h-7' : 'w-5 h-5';
  const textSize = size === 'lg' ? 'text-base' : 'text-xs';
  return (
    <Button
      type="button"
      variant="outline"
      className={`flex flex-col justify-center items-center gap-1 text-gray-700 hover:bg-gray-100 hover:text-blue-600 transition-colors disabled:opacity-50 p-2 ${btnSize}`}
      onClick={() => onClick(type)}
      disabled={disabled}
      style={{ minWidth: 0 }}
    >
      <Icon className={`${iconSize} ${colorClass}`} />
      <span className={`${textSize} font-medium text-gray-600 text-center leading-tight`} style={{ wordBreak: 'break-word' }}>{type.charAt(0).toUpperCase() + type.slice(1)}</span>
      {type === 'commercial' && disabled && (
        <span className="text-[11px] text-gray-400 mt-1">Coming soon</span>
      )}
    </Button>
  );
};

export default AddSegmentButton;
