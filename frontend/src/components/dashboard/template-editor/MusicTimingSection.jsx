import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatDisplayName } from "@/lib/displayNames";
import { Separator } from "@/components/ui/separator";
import {
  DEFAULT_VOLUME_LEVEL,
  MUSIC_VOLUME_LEVELS,
  describeVolumeLevel,
  volumeDbToLevel,
} from "./constants";
import {
  Globe,
  HelpCircle,
  Lightbulb,
  ListChecks,
  Loader2,
  Plus,
  Settings2,
  Trash2,
  Upload,
} from "lucide-react";

const MusicTimingSection = ({
  isOpen,
  onToggle,
  template,
  onTimingChange,
  backgroundMusicRules,
  onBackgroundMusicChange,
  onAddBackgroundMusicRule,
  onRemoveBackgroundMusicRule,
  musicFiles,
  onStartMusicUpload,
  musicUploadIndex,
  isUploadingMusic,
  musicUploadInputRef,
  onMusicFileSelected,
  onSetMusicVolumeLevel,
  voiceName,
  onChooseVoice,
  internVoiceDisplay,
  onChooseInternVoice,
  globalMusicAssets = [],
}) => (
  <div data-tour="template-advanced" data-tour-id="template-music-timing">
    <div className="mt-10 flex items-center justify-between">
      <h2 className="text-lg font-semibold">Music &amp; Timing Options</h2>
      <Button variant="outline" size="sm" onClick={onToggle}>
        {isOpen ? "Hide options" : "Show options"}
      </Button>
    </div>
    {isOpen && (
      <div className="grid gap-6 lg:grid-cols-[2fr_1fr] mt-6">
        <div className="space-y-6">
          <Card data-tour-id="template-timing-controls">
            <CardHeader className="flex flex-col gap-2">
              <CardTitle className="flex items-center gap-2">
                <Settings2 className="w-6 h-6 text-gray-600" /> Music &amp; timing controls
              </CardTitle>
              <CardDescription>
                Fine-tune when segments fire and how the background music behaves.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5 pt-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div data-tour-id="template-overlap-intro">
                  <Label className="flex items-center gap-1">
                    Intro/Content Overlap (seconds)
                    <HelpCircle
                      className="h-3.5 w-3.5 text-muted-foreground"
                      aria-hidden="true"
                      title="How many seconds the intro and content overlap. Positive values create smooth transitions."
                    />
                  </Label>
                  <Input
                    type="number"
                    step="0.5"
                    min="0"
                    value={Math.abs(template.timing?.content_start_offset_s || 0)}
                    onChange={(e) => {
                      const val = parseFloat(e.target.value || 0);
                      // Convert positive input to negative offset (overlap behavior)
                      onTimingChange("content_start_offset_s", val > 0 ? -Math.abs(val) : 0);
                    }}
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Positive values overlap intro with content. Default 0 (no overlap).
                  </p>
                </div>
                <div>
                  <Label className="flex items-center gap-1">
                    Content/Outro Overlap (seconds)
                    <HelpCircle
                      className="h-3.5 w-3.5 text-muted-foreground"
                      aria-hidden="true"
                      title="How many seconds the content and outro overlap. Positive values create smooth transitions."
                    />
                  </Label>
                  <Input
                    type="number"
                    step="0.5"
                    min="0"
                    value={Math.abs(template.timing?.outro_start_offset_s || 0)}
                    onChange={(e) => {
                      const val = parseFloat(e.target.value || 0);
                      // Convert positive input to negative offset (overlap behavior)
                      onTimingChange("outro_start_offset_s", val > 0 ? -Math.abs(val) : 0);
                    }}
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Positive values overlap content with outro. Default 0 (no overlap).
                  </p>
                </div>
              </div>

              <div>
                <h4 className="text-lg font-semibold mb-2 flex items-center gap-1">
                  Background Music
                  <HelpCircle
                    className="h-4 w-4 text-muted-foreground"
                    aria-hidden="true"
                    title="Apply looping music or stingers to specific sections."
                  />
                </h4>
                <div className="space-y-4">
                  {backgroundMusicRules.map((rule, index) => (
                    <div key={rule.id} className="p-4 border rounded-lg bg-gray-50 space-y-4">
                      <div className="flex justify-between items-center">
                        <Label className="font-semibold">Music Rule #{index + 1}</Label>
                        <Button variant="destructive" size="sm" onClick={() => onRemoveBackgroundMusicRule(index)}>
                          <Trash2 className="w-4 h-4 mr-2" />
                          Remove
                        </Button>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <Label>Apply to Section</Label>
                          <Select
                            value={rule.apply_to_segments[0]}
                            onValueChange={(v) => onBackgroundMusicChange(index, "apply_to_segments", [v])}
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="intro">Intro</SelectItem>
                              <SelectItem value="content">Content</SelectItem>
                              <SelectItem value="outro">Outro</SelectItem>
                              <SelectItem value="commercial">Commercial</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div>
                          <Label>Music File</Label>
                          {rule.music_asset_id ? (
                            <div className="space-y-2">
                              <div className="flex items-center gap-2">
                                <div className="flex-1 px-3 py-2 border rounded-md bg-blue-50 border-blue-200">
                                  <div className="flex items-center gap-2">
                                    <Globe className="w-4 h-4 text-blue-600" />
                                    <span className="text-sm font-medium">
                                      {(() => {
                                        const asset = globalMusicAssets.find(a => a.id === rule.music_asset_id);
                                        return asset?.display_name || 'Global Music Track';
                                      })()}
                                    </span>
                                  </div>
                                  {(() => {
                                    const asset = globalMusicAssets.find(a => a.id === rule.music_asset_id);
                                    if (asset?.duration_s) {
                                      const mins = Math.floor(asset.duration_s / 60);
                                      const secs = Math.floor(asset.duration_s % 60);
                                      return (
                                        <p className="text-xs text-muted-foreground mt-1">
                                          Duration: {mins}:{String(secs).padStart(2, '0')}
                                        </p>
                                      );
                                    }
                                    return null;
                                  })()}
                                </div>
                              </div>
                              {/* Quick swap dropdown for global music tracks */}
                              {globalMusicAssets.length > 1 && (
                                <div className="flex items-center gap-2">
                                  <Select
                                    value={rule.music_asset_id}
                                    onValueChange={(v) => onBackgroundMusicChange(index, "music_asset_id", v)}
                                  >
                                    <SelectTrigger className="flex-1">
                                      <SelectValue placeholder="Swap to..." />
                                    </SelectTrigger>
                                    <SelectContent>
                                      {globalMusicAssets.map((asset) => (
                                        <SelectItem key={asset.id} value={asset.id}>
                                          <div className="flex items-center gap-2">
                                            <Globe className="w-3 h-3" />
                                            {asset.display_name}
                                          </div>
                                        </SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    onClick={() => {
                                      onBackgroundMusicChange(index, "music_asset_id", null);
                                    }}
                                    title="Switch to uploaded file instead"
                                  >
                                    Use File
                                  </Button>
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <Select
                                value={rule.music_filename}
                                onValueChange={(v) => {
                                  // Check if this is a global music asset ID (starts with numbers/letters, not a filename)
                                  const isGlobalAsset = globalMusicAssets.some(a => a.id === v);
                                  if (isGlobalAsset) {
                                    // User selected global music - set music_asset_id instead
                                    onBackgroundMusicChange(index, "music_asset_id", v);
                                    onBackgroundMusicChange(index, "music_filename", null);
                                  } else {
                                    // User selected uploaded file
                                    onBackgroundMusicChange(index, "music_filename", v);
                                  }
                                }}
                              >
                                <SelectTrigger>
                                  <SelectValue placeholder="Select music..." />
                                </SelectTrigger>
                                <SelectContent>
                                  {/* Global music assets first */}
                                  {globalMusicAssets.length > 0 && (
                                    <>
                                      <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">Global Music</div>
                                      {globalMusicAssets.map((asset) => (
                                        <SelectItem key={asset.id} value={asset.id}>
                                          <div className="flex items-center gap-2">
                                            <Globe className="w-3 h-3" />
                                            {asset.display_name}
                                          </div>
                                        </SelectItem>
                                      ))}
                                    </>
                                  )}
                                  {/* Uploaded files */}
                                  {musicFiles.length > 0 && (
                                    <>
                                      {globalMusicAssets.length > 0 && <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground border-t">Uploaded Files</div>}
                                      {musicFiles.map((f) => (
                                        <SelectItem key={f.id} value={f.filename}>
                                          {formatDisplayName(f, { fallback: f.friendly_name || 'Audio clip' }) || 'Audio clip'}
                                        </SelectItem>
                                      ))}
                                    </>
                                  )}
                                </SelectContent>
                              </Select>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => onStartMusicUpload(index)}
                                disabled={isUploadingMusic && musicUploadIndex === index}
                              >
                                {isUploadingMusic && musicUploadIndex === index ? (
                                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                ) : (
                                  <Upload className="w-4 h-4 mr-2" />
                                )}
                                Upload
                              </Button>
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                          <Label>Start Offset (sec)</Label>
                          <Input
                            type="number"
                            step="0.5"
                            value={rule.start_offset_s}
                            onChange={(e) => onBackgroundMusicChange(index, "start_offset_s", parseFloat(e.target.value || 0))}
                          />
                        </div>
                        <div>
                          <Label>End Offset (sec)</Label>
                          <Input
                            type="number"
                            step="0.5"
                            value={rule.end_offset_s}
                            onChange={(e) => onBackgroundMusicChange(index, "end_offset_s", parseFloat(e.target.value || 0))}
                          />
                        </div>
                        <div>
                          <Label>Fade In (sec)</Label>
                          <Input
                            type="number"
                            step="0.5"
                            value={rule.fade_in_s}
                            onChange={(e) => onBackgroundMusicChange(index, "fade_in_s", parseFloat(e.target.value || 0))}
                          />
                        </div>
                        <div>
                          <Label>Fade Out (sec)</Label>
                          <Input
                            type="number"
                            step="0.5"
                            value={rule.fade_out_s}
                            onChange={(e) => onBackgroundMusicChange(index, "fade_out_s", parseFloat(e.target.value || 0))}
                          />
                        </div>
                      </div>
                      <div className="mt-4 space-y-2">
                        <div className="flex items-center justify-between">
                          <Label className="flex items-center gap-1">Loudness</Label>
                          <span className="text-xs text-muted-foreground">Scale 1–11</span>
                        </div>
                        <div className="space-y-2">
                          {(() => {
                            const level = volumeDbToLevel(rule.volume_db);
                            const displayLevel = Number.isFinite(level) ? level : DEFAULT_VOLUME_LEVEL;
                            return (
                              <>
                                <div className="flex items-center gap-3">
                                  <Input
                                    type="range"
                                    min="1"
                                    max="11"
                                    step="0.1"
                                    value={displayLevel}
                                    onChange={(e) => onSetMusicVolumeLevel(index, parseFloat(e.target.value))}
                                    className="w-full"
                                  />
                                  <Input
                                    type="number"
                                    min="1"
                                    max="11"
                                    step="0.1"
                                    value={displayLevel.toFixed(1)}
                                    onChange={(e) => onSetMusicVolumeLevel(index, parseFloat(e.target.value))}
                                    className="w-24"
                                  />
                                </div>
                                <div className="grid grid-cols-11 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                                  {MUSIC_VOLUME_LEVELS.map(({ level: presetLevel }) => (
                                    <span key={presetLevel} className="text-center">
                                      {presetLevel}
                                    </span>
                                  ))}
                                </div>
                                <p className="text-xs text-gray-500">{describeVolumeLevel(displayLevel)}</p>
                              </>
                            );
                          })()}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <input
                  ref={musicUploadInputRef}
                  type="file"
                  accept="audio/*"
                  className="hidden"
                  onChange={onMusicFileSelected}
                />
                <Button onClick={onAddBackgroundMusicRule} variant="outline" className="mt-4">
                  <Plus className="w-4 h-4 mr-2" />Add Music Rule
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle className="text-base">AI voice defaults</CardTitle>
              <CardDescription>Choose which voices power automated narration.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <Label className="text-sm font-medium text-gray-600 flex items-center gap-1">
                    Default AI Voice
                    <HelpCircle
                      className="h-4 w-4 text-muted-foreground"
                      aria-hidden="true"
                      title="Set a default voice for template AI voice prompts."
                    />
                  </Label>
                  <div className="text-sm text-gray-800 mt-1">{voiceName || "Not set"}</div>
                </div>
                <div className="mt-2 sm:mt-0">
                  <Button variant="outline" onClick={onChooseVoice}>
                    Choose voice
                  </Button>
                </div>
              </div>
              <Separator />
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <Label className="text-sm font-medium text-gray-600 flex items-center gap-1">
                    Intern Command Voice
                    <HelpCircle
                      className="h-4 w-4 text-muted-foreground"
                      aria-hidden="true"
                      title="Used when the Intern command creates narrated edits."
                    />
                  </Label>
                  <div className="text-sm text-gray-800 mt-1">{internVoiceDisplay}</div>
                </div>
                <div className="mt-2 sm:mt-0">
                  <Button variant="outline" onClick={onChooseInternVoice}>
                    Choose voice
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border border-slate-200 bg-slate-50 self-start">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2 text-slate-800">
                <Lightbulb className="h-4 w-4 text-amber-500" aria-hidden="true" />
                Background music cheat sheet
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-slate-700">
              <p>
                Need a refresher on how the controls interact? Keep these guidelines in mind while you dial things in.
              </p>
              <ul className="space-y-2">
                <li className="flex items-start gap-2">
                  <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
                  <span>
                    <strong>Offsets</strong> slide music earlier or later. Positive values create overlaps (crossfades) with the 
                    neighboring segment. Zero means segments play back-to-back with no gaps.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
                  <span>
                    <strong>Fade in/out</strong> smooth the transitions. Longer fades work best for ambient tracks, shorter fades for
                    stingers.
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
                  <span>
                    <strong>Loudness</strong> now uses a 1–11 scale: 1 is barely audible, 10 matches the host, and 11 pushes the music slightly hotter.
                  </span>
                </li>
              </ul>
              <p className="text-xs text-slate-500">
                Save when things sound right—your episode builder will inherit these timing rules.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    )}
  </div>
);

export default MusicTimingSection;
