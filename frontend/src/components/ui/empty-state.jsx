import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

/**
 * EmptyState component for displaying helpful empty states with CTAs
 * 
 * @param {Object} props
 * @param {string} props.title - Main title/heading
 * @param {string} props.description - Description text explaining the empty state
 * @param {React.ReactNode} props.icon - Icon component (from lucide-react)
 * @param {Object} props.action - Action button configuration
 * @param {string} props.action.label - Button label
 * @param {Function} props.action.onClick - Button click handler
 * @param {string} props.action.variant - Button variant (default: "default")
 * @param {React.ReactNode} props.children - Additional content to display
 */
export function EmptyState({ 
  title, 
  description, 
  icon: Icon, 
  action,
  children 
}) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center justify-center py-12 px-6 text-center">
        {Icon && (
          <div className="mb-4 p-3 rounded-full bg-muted">
            <Icon className="w-8 h-8 text-muted-foreground" />
          </div>
        )}
        <h3 className="text-lg font-semibold mb-2">{title}</h3>
        {description && (
          <p className="text-sm text-muted-foreground mb-6 max-w-md">
            {description}
          </p>
        )}
        {action && (
          <Button 
            onClick={action.onClick}
            variant={action.variant || "default"}
            className="mb-4"
          >
            {action.icon && <action.icon className="w-4 h-4 mr-2" />}
            {action.label}
          </Button>
        )}
        {children}
      </CardContent>
    </Card>
  );
}



