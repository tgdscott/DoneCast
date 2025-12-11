import React, { useState, useEffect } from "react";
import { AudioWaveform, Save, RefreshCw } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { makeApi } from "@/lib/apiClient";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { SectionCard, SectionItem } from "@/components/dashboard/SettingsSections";
import { useToast } from "@/hooks/use-toast";

const QUALITY_THRESHOLDS = [
    {
        value: "good",
        label: "Excellent",
        description: "Use advanced processing even for high-quality audio",
    },
    {
        value: "slightly_bad",
        label: "Pretty Good",
        description: "Use advanced processing for anything less than excellent",
    },
    {
        value: "fairly_bad",
        label: "Fair",
        description: "Use advanced processing when quality becomes noticeable",
    },
    {
        value: "very_bad",
        label: "Needs Work",
        description: "Use advanced processing only for problematic audio (recommended)",
        recommended: true,
    },
    {
        value: "incredibly_bad",
        label: "Problematic",
        description: "Use advanced processing only for severely degraded audio",
    },
    {
        value: "abysmal",
        label: "Abysmal",
        description: "Use advanced processing only for the worst quality audio",
    },
];

export default function AudioProcessingSettings() {
    const { token } = useAuth();
    const { toast } = useToast();
    const [threshold, setThreshold] = useState("very_bad");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [dirty, setDirty] = useState(false);

    useEffect(() => {
        loadSettings();
    }, [token]);

    const loadSettings = async () => {
        if (!token) return;
        setLoading(true);
        try {
            const data = await makeApi(token).get("/api/users/me/audio-pipeline");
            setThreshold(data?.audio_processing_threshold_label || "very_bad");
            setDirty(false);
        } catch (err) {
            toast({
                title: "Failed to load settings",
                description: err?.message || "Please try again.",
                variant: "destructive",
            });
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await makeApi(token).put("/api/users/me/audio-pipeline", {
                audio_processing_threshold_label: threshold,
            });
            toast({ title: "Audio processing settings saved successfully" });
            setDirty(false);
        } catch (err) {
            toast({
                title: "Failed to save settings",
                description: err?.message || "Please try again.",
                variant: "destructive",
            });
        } finally {
            setSaving(false);
        }
    };

    const handleThresholdChange = (value) => {
        setThreshold(value);
        setDirty(true);
    };

    if (loading) {
        return (
            <SectionCard
                icon={<AudioWaveform className="h-5 w-5 text-white" />}
                title="Audio Processing Quality"
                subtitle="Loading your preferences..."
                defaultOpen
            >
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Loading...
                </div>
            </SectionCard>
        );
    }

    return (
        <SectionCard
            icon={<AudioWaveform className="h-5 w-5 text-white" />}
            title="Audio Processing Quality"
            subtitle="Choose when to use advanced audio processing based on detected quality"
            defaultOpen
        >
            <SectionItem
                icon={<AudioWaveform className="h-4 w-4 text-white" />}
                title="Quality Threshold"
                description="Advanced processing (Auphonic) will be used when your audio quality is at or below this threshold. Higher quality audio can use standard processing to save costs."
            >
                <div className="space-y-4">
                    <RadioGroup value={threshold} onValueChange={handleThresholdChange}>
                        <div className="space-y-3">
                            {QUALITY_THRESHOLDS.map((option) => (
                                <div
                                    key={option.value}
                                    className={`relative flex items-start space-x-3 rounded-lg border p-4 transition-colors ${threshold === option.value
                                        ? "border-blue-500 bg-blue-50"
                                        : "border-slate-200 bg-white hover:border-slate-300"
                                        }`}
                                >
                                    <RadioGroupItem
                                        value={option.value}
                                        id={option.value}
                                        className="mt-1"
                                    />
                                    <div className="flex-1 space-y-1">
                                        <div className="flex items-center gap-2">
                                            <Label
                                                htmlFor={option.value}
                                                className="text-sm font-semibold text-slate-900 cursor-pointer"
                                            >
                                                {option.label}
                                            </Label>
                                            {option.recommended && (
                                                <span className="px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 rounded-full">
                                                    Recommended
                                                </span>
                                            )}
                                        </div>
                                        <p className="text-xs text-slate-600">
                                            {option.description}
                                        </p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </RadioGroup>

                    <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
                        <p className="font-medium mb-1">How it works:</p>
                        <p className="text-xs">
                            All uploads are automatically analyzed for audio quality. If the
                            detected quality is <strong>at or below</strong> your selected
                            threshold, advanced processing (Auphonic) will be used to improve
                            it. Otherwise, standard processing is used to save costs.
                        </p>
                    </div>

                    <div className="flex items-center justify-between pt-2">
                        <span className="text-xs text-muted-foreground">
                            {dirty ? "You have unsaved changes" : "All changes saved"}
                        </span>
                        <Button
                            onClick={handleSave}
                            disabled={!dirty || saving}
                            className="gap-2"
                        >
                            {saving ? (
                                <>
                                    <RefreshCw className="h-4 w-4 animate-spin" />
                                    Saving...
                                </>
                            ) : (
                                <>
                                    <Save className="h-4 w-4" />
                                    Save settings
                                </>
                            )}
                        </Button>
                    </div>
                </div>
            </SectionItem>
        </SectionCard>
    );
}
