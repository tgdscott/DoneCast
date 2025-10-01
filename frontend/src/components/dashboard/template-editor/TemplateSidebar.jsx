import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Compass } from "lucide-react";

const TemplateSidebar = ({ template, onToggleActive, onStartTour }) => (
  <aside className="space-y-6 xl:sticky xl:top-24">
    <Card className="border border-slate-200 bg-slate-50" data-tour="template-quickstart">
      <CardHeader className="flex flex-col gap-1 pb-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 text-slate-800">
          <Compass className="h-5 w-5 text-primary" aria-hidden="true" />
          <CardTitle className="text-base">Template quickstart</CardTitle>
        </div>
        <CardDescription className="text-sm text-slate-600 sm:text-right">
          Three checkpoints to get from blank template to publish-ready episodes.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-slate-700">
        <ol className="list-decimal space-y-1 pl-5">
          <li>Name the template and attach it to the show it powers.</li>
          <li>Add intro, content, and outro segments—drag to match your flow.</li>
          <li>Open Music &amp; Timing Options to dial in fades, offsets, and beds.</li>
        </ol>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-xs text-slate-500">Prefer a tour? We’ll highlight each area for you.</span>
          <Button variant="outline" size="sm" onClick={onStartTour}>
            Start guided tour
          </Button>
        </div>
      </CardContent>
    </Card>

    <Card className="shadow-sm" data-tour="template-status">
      <CardContent className="p-6 flex items-center justify-between">
        <div>
          <CardTitle className="text-lg">Template status</CardTitle>
          <CardDescription>Mark a template inactive to hide it from selection without deleting it.</CardDescription>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`text-sm px-2 py-1 rounded-full border ${
              template?.is_active !== false
                ? "bg-green-50 text-green-700 border-green-200"
                : "bg-gray-100 text-gray-700 border-gray-300"
            }`}
          >
            {template?.is_active !== false ? "Active" : "Inactive"}
          </span>
          <Button variant="outline" onClick={onToggleActive}>
            {template?.is_active !== false ? "Disable" : "Enable"}
          </Button>
        </div>
      </CardContent>
    </Card>
  </aside>
);

export default TemplateSidebar;
