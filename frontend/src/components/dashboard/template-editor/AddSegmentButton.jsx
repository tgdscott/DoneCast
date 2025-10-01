import { Button } from "@/components/ui/button";
import { segmentIcons } from "./constants";

const AddSegmentButton = ({ type, onClick, disabled }) => (
  <Button
    type="button"
    variant="outline"
    className="flex flex-col h-20 justify-center items-center gap-2 text-gray-700 hover:bg-gray-100 hover:text-blue-600 transition-colors disabled:opacity-50"
    onClick={() => onClick(type)}
    disabled={disabled}
  >
    {segmentIcons[type]}
    <span className="text-sm font-semibold">{type.charAt(0).toUpperCase() + type.slice(1)}</span>
  </Button>
);

export default AddSegmentButton;
