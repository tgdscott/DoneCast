import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  ArrowLeft,
  Upload,
  FileAudio,
  Wand2,
  Play,
  Pause,
  Calendar,
  Clock,
  CheckCircle,
  Mic,
  Settings,
  Sparkles,
  Eye,
  Share2,
  Zap,
  Target,
  TrendingUp,
  Volume2,
  BarChart3,
  MessageSquare,
  Globe,
  Lightbulb,
  Star,
  Download,
  RefreshCw,
} from "lucide-react"
import { useState, useRef, useEffect } from "react"
import EpisodePublishTimeline from "@/components/EpisodePublishTimeline.jsx"
import EpisodeStructureSummary from "@/components/EpisodeStructureSummary.jsx"
import EpisodeSegmentEditor from "@/components/EpisodeSegmentEditor.jsx"

export default function PodcastCreator() {
  const [currentStep, setCurrentStep] = useState(1)
  const [isPlaying, setIsPlaying] = useState(false)
  const [uploadedFile, setUploadedFile] = useState(null)
  const [generatedAudio, setGeneratedAudio] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const fileInputRef = useRef(null)

  const [formData, setFormData] = useState({
    contentType: "", // "upload" or "generate"
    audioFile: null,
    scriptText: "",
    episodeTitle: "",
    episodeDescription: "",
    autoEnhancement: true,
    removeSilences: true,
    addIntroOutro: true,
    generateChapters: true,
    voiceType: "natural",
  publishOption: "draft", // "now" or "schedule"
    scheduleDate: "",
    scheduleTime: "",
    tags: [],
    category: "",
    generateArtwork: true,
    generateSocialPosts: true,
  })

  const [aiSuggestions, setAiSuggestions] = useState({
    title: "",
    description: "",
    tags: [],
    estimatedListeners: 0,
    seoScore: 0,
  })

  const [audioAnalysis, setAudioAnalysis] = useState({
    duration: "0:00",
    quality: "Good",
    loudness: "Optimal",
    silenceRemoved: "2.3s",
    enhancementsApplied: 3,
  })

  // Basic derived total seconds (rough parse of m:ss)
  const totalSeconds = (() => {
    const m = /^(\d+):(\d{1,2})$/.exec(audioAnalysis.duration || '');
    if (!m) return 0;
    return parseInt(m[1],10)*60 + parseInt(m[2],10);
  })();

  const [segments, setSegments] = useState(() => [
    { id: crypto.randomUUID(), label: 'Intro', start: 0, end:  Math.max(15, Math.min(45,  Math.round(totalSeconds*0.05))) || 30, type: 'intro' },
    { id: crypto.randomUUID(), label: 'Main Segment', start:  Math.max(15, Math.min(45,  Math.round(totalSeconds*0.05))) || 30, end: totalSeconds ? Math.max( Math.round(totalSeconds*0.85), 120) : 240, type: 'main' },
    { id: crypto.randomUUID(), label: 'Outro', start: totalSeconds ? Math.max( Math.round(totalSeconds*0.85), 120) : 240, end: totalSeconds || 360, type: 'outro' },
  ]);

  // Recalculate core segment boundaries if duration changes (e.g., after analysis)
  useEffect(() => {
    if (!totalSeconds || segments.some(s=>s.type==='ad')) return; // skip if ads inserted or no duration
    const introLen = Math.max(15, Math.min(45, Math.round(totalSeconds*0.05)));
    const outroStart = Math.max(Math.round(totalSeconds*0.85), introLen + 60);
    setSegments([
      { ...segments[0], start:0, end:introLen, type:'intro', label:segments[0].label || 'Intro' },
      { ...segments[1], start:introLen, end:Math.min(outroStart, totalSeconds-30), type:'main', label:segments[1].label || 'Main Segment' },
      { ...segments[2], start:Math.min(outroStart, totalSeconds-30), end: totalSeconds, type:'outro', label:segments[2].label || 'Outro' },
    ]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioAnalysis.duration]);

  const steps = [
    { number: 1, title: "Add Content", description: "Upload audio or generate from text", icon: Mic },
    { number: 2, title: "Details & Review", description: "Episode information and settings", icon: Settings },
    { number: 3, title: "Publish", description: "Schedule or publish your episode", icon: Globe },
  ]

  const progressPercentage = (currentStep / steps.length) * 100

  const voiceOptions = [
    { value: "natural", label: "Natural Voice", description: "Warm, conversational tone" },
    { value: "professional", label: "Professional", description: "Clear, authoritative voice" },
    { value: "friendly", label: "Friendly", description: "Upbeat, engaging tone" },
    { value: "calm", label: "Calm", description: "Soothing, relaxed voice" },
  ]

  const categoryOptions = [
    "Business",
    "Education",
    "Entertainment",
    "Health & Fitness",
    "News",
    "Society & Culture",
    "Technology",
    "True Crime",
    "Comedy",
    "Sports",
    "Arts",
    "Science",
  ]

  // Helper to format filenames for display (strip UUID/hash prefixes, extension, prettify)
  const formatDisplayName = (name) => {
    try {
      if (!name) return '';
      let s = name.split(/[\\/]/).pop();
      s = s.replace(/\.[a-z0-9]{2,5}$/i, '');
      s = s.replace(/^(?:[a-f0-9]{8,}|[a-f0-9-]{20,})[_-]+/i, '');
      s = s.replace(/[._-]+/g, ' ').trim();
      if (s.length) s = s[0].toUpperCase() + s.slice(1);
      return s;
    } catch { return name; }
  };

  const handleFileUpload = (file) => {
    setUploadedFile(file)
    setFormData({ ...formData, audioFile: file, contentType: "upload" })
    setIsAnalyzing(true)

    // Simulate audio analysis
    setTimeout(() => {
      setIsAnalyzing(false)
      setAudioAnalysis({
        duration: "5:47",
        quality: "Excellent",
        loudness: "Optimal",
        silenceRemoved: "2.3s",
        enhancementsApplied: 3,
      })
    }, 2000)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    setIsDragOver(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    setIsDragOver(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragOver(false)
    const files = e.dataTransfer.files
    if (files.length > 0) {
      handleFileUpload(files[0])
    }
  }

  const handleFileInputChange = (e) => {
    const files = e.target.files
    if (files && files.length > 0) {
      handleFileUpload(files[0])
    }
  }

  const handleGenerateAudio = () => {
    if (formData.scriptText.trim()) {
      setIsGenerating(true)
      setFormData({ ...formData, contentType: "generate" })

      // Simulate AI generation
      setTimeout(() => {
        setIsGenerating(false)
        setGeneratedAudio(true)
        setAudioAnalysis({
          duration: "4:23",
          quality: "Excellent",
          loudness: "Optimal",
          silenceRemoved: "0s",
          enhancementsApplied: 2,
        })
      }, 3000)
    }
  }

  const generateAISuggestions = () => {
    if (formData.scriptText.trim() || uploadedFile) {
      // Simulate AI analysis and suggestions
      setTimeout(() => {
        setAiSuggestions({
          title: "My Journey Through Summer Adventures",
          description:
            "Join me as I share the incredible experiences and life lessons from my summer travels. From unexpected encounters to moments of self-discovery, this episode explores how stepping out of our comfort zone can lead to the most meaningful adventures.",
          tags: ["travel", "personal growth", "summer", "adventures", "life lessons"],
          estimatedListeners: 245,
          seoScore: 85,
        })
      }, 1000)
    }
  }

  useEffect(() => {
    if (currentStep === 2 && (uploadedFile || generatedAudio)) {
      generateAISuggestions()
    }
  }, [currentStep, uploadedFile, generatedAudio])

  const canProceedToStep2 = uploadedFile || (generatedAudio && formData.scriptText.trim())
  const canProceedToStep3 = formData.episodeTitle.trim() && formData.episodeDescription.trim()

  const handleNextStep = () => {
    if (currentStep < 3) {
      setCurrentStep(currentStep + 1)
    }
  }

  const handlePreviousStep = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1)
    }
  }

  const handlePublish = () => {
    // Simulate publishing
    alert("Episode published successfully! 🎉")
  }

  const addTag = (tag) => {
    if (tag && !formData.tags.includes(tag)) {
      setFormData({ ...formData, tags: [...formData.tags, tag] })
    }
  }

  const removeTag = (tagToRemove) => {
    setFormData({ ...formData, tags: formData.tags.filter((tag) => tag !== tagToRemove) })
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 px-4 py-6 bg-white shadow-sm">
        <div className="container mx-auto max-w-6xl">
          <div className="flex items-center justify-between">
            <Button
              variant="ghost"
              className="text-gray-600 hover:text-gray-800 hover:bg-gray-100"
              onClick={() => window.history.back()}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Dashboard
            </Button>
            <div className="text-center">
              <h1 className="text-3xl md:text-4xl font-bold" style={{ color: "#2C3E50" }}>
                Podcast Creator
              </h1>
              <p className="text-gray-600 mt-1">Create your next episode in minutes</p>
            </div>
            <div className="flex items-center space-x-2">
              <Button variant="ghost" size="sm" className="text-gray-600">
                <Eye className="w-4 h-4 mr-1" />
                Preview
              </Button>
              <Button variant="ghost" size="sm" className="text-gray-600">
                Save Draft
              </Button>
            </div>
          </div>
        </div>
      </header>
      {/* Enhanced Progress Indicator */}
      <div className="px-4 py-6 bg-white border-b border-gray-100">
        <div className="container mx-auto max-w-6xl">
          <div className="mb-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-gray-600">Progress</span>
              <span className="text-sm font-medium" style={{ color: "#2C3E50" }}>
                Step {currentStep} of {steps.length}
              </span>
            </div>
            <Progress value={progressPercentage} className="h-2 mb-6" />
            <div className="flex justify-between">
              {steps.map((step) => (
                <div
                  key={step.number}
                  className={`flex flex-col items-center transition-all ${
                    currentStep >= step.number ? "text-blue-600" : "text-gray-400"
                  }`}>
                  <div
                    className={`w-12 h-12 rounded-full flex items-center justify-center mb-3 transition-all ${
                      currentStep >= step.number ? "text-white shadow-lg" : "bg-gray-100 text-gray-400"
                    }`}
                    style={{
                      backgroundColor: currentStep >= step.number ? "#2C3E50" : undefined,
                    }}>
                    {currentStep > step.number ? (
                      <CheckCircle className="w-6 h-6" />
                    ) : (
                      <step.icon className="w-6 h-6" />
                    )}
                  </div>
                  <div className="text-center">
                    <div className="font-semibold text-sm">{step.title}</div>
                    <div className="text-xs text-gray-500 hidden sm:block max-w-24">{step.description}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      {/* Main Content */}
      <main className="container mx-auto max-w-6xl px-4 py-8">
        {/* Step 1: Add Content */}
        {currentStep === 1 && (
          <div className="space-y-8">
            <div className="text-center mb-8">
              <h2 className="text-3xl font-bold mb-3" style={{ color: "#2C3E50" }}>
                Add Your Content
              </h2>
              <p className="text-gray-600 text-lg max-w-2xl mx-auto">
                Upload an existing audio file or let our AI create professional-quality speech from your script
              </p>
            </div>

            <Tabs defaultValue="upload" className="max-w-4xl mx-auto">
              <TabsList className="grid w-full grid-cols-2 mb-8">
                <TabsTrigger value="upload" className="text-lg py-3">
                  <Upload className="w-5 h-5 mr-2" />
                  Upload Audio
                </TabsTrigger>
                <TabsTrigger value="generate" className="text-lg py-3">
                  <Wand2 className="w-5 h-5 mr-2" />
                  Generate with AI
                </TabsTrigger>
              </TabsList>

              <TabsContent value="upload" className="space-y-6">
                <Card
                  className="border-2 border-dashed border-gray-200 hover:border-gray-300 transition-all bg-white">
                  <CardContent className="p-8">
                    <div
                      className={`border-2 border-dashed rounded-xl p-12 text-center transition-all ${
                        isDragOver
                          ? "border-blue-400 bg-blue-50 scale-105"
                          : uploadedFile
                            ? "border-green-400 bg-green-50"
                            : "border-gray-300 hover:border-gray-400 hover:bg-gray-50"
                      }`}
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}>
                      {uploadedFile ? (
                        <div className="space-y-6">
                          <div className="relative">
                            <FileAudio className="w-16 h-16 mx-auto text-green-600" />
                            <CheckCircle
                              className="w-6 h-6 absolute -top-1 -right-1 text-green-600 bg-white rounded-full" />
                          </div>
                          <div>
                            <p className="text-xl font-semibold text-green-600 mb-2">File uploaded successfully!</p>
                            <p className="text-gray-600 mb-1">{formatDisplayName(uploadedFile.name)}</p>
                            <p className="text-sm text-gray-500">{(uploadedFile.size / (1024 * 1024)).toFixed(1)} MB</p>
                          </div>

                          {isAnalyzing ? (
                            <div className="flex items-center justify-center space-x-2 text-blue-600">
                              <RefreshCw className="w-4 h-4 animate-spin" />
                              <span>Analyzing audio quality...</span>
                            </div>
                          ) : (
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                              <div className="bg-white p-3 rounded-lg border">
                                <div className="font-semibold text-gray-800">Duration</div>
                                <div className="text-blue-600">{audioAnalysis.duration}</div>
                              </div>
                              <div className="bg-white p-3 rounded-lg border">
                                <div className="font-semibold text-gray-800">Quality</div>
                                <div className="text-green-600">{audioAnalysis.quality}</div>
                              </div>
                              <div className="bg-white p-3 rounded-lg border">
                                <div className="font-semibold text-gray-800">Loudness</div>
                                <div className="text-blue-600">{audioAnalysis.loudness}</div>
                              </div>
                              <div className="bg-white p-3 rounded-lg border">
                                <div className="font-semibold text-gray-800">Enhancements</div>
                                <div className="text-purple-600">{audioAnalysis.enhancementsApplied} applied</div>
                              </div>
                            </div>
                          )}

                          <Button
                            variant="outline"
                            onClick={() => fileInputRef.current?.click()}
                            className="mt-4">
                            Choose Different File
                          </Button>
                        </div>
                      ) : (
                        <div className="space-y-6">
                          <div className="relative">
                            <Mic className="w-16 h-16 mx-auto text-gray-400" />
                            {isDragOver && (
                              <div className="absolute inset-0 flex items-center justify-center">
                                <div
                                  className="w-20 h-20 border-4 border-blue-400 border-dashed rounded-full animate-pulse"></div>
                              </div>
                            )}
                          </div>
                          <div>
                            <p className="text-2xl font-semibold text-gray-700 mb-2">
                              {isDragOver ? "Drop your file here!" : "Drag your audio file here"}
                            </p>
                            <p className="text-gray-500 mb-6">or click to browse your computer</p>
                          </div>
                          <Button
                            onClick={() => fileInputRef.current?.click()}
                            size="lg"
                            className="text-white px-8 py-3"
                            style={{ backgroundColor: "#2C3E50" }}>
                            <Upload className="w-5 h-5 mr-2" />
                            Choose Audio File
                          </Button>
                        </div>
                      )}
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="audio/*"
                        onChange={handleFileInputChange}
                        className="hidden" />
                    </div>
                    <CreatorUploadHint />
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="generate" className="space-y-6">
                <Card className="border-0 shadow-lg bg-white">
                  <CardHeader>
                    <CardTitle className="flex items-center text-2xl" style={{ color: "#2C3E50" }}>
                      <Sparkles className="w-6 h-6 mr-3" />
                      AI Voice Generation
                    </CardTitle>
                    <p className="text-gray-600">Transform your script into professional-quality audio</p>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="grid md:grid-cols-3 gap-4 mb-6">
                      <div>
                        <Label className="text-sm font-medium text-gray-700 mb-2 block">Voice Style</Label>
                        <Select
                          value={formData.voiceType}
                          onValueChange={(value) => setFormData({ ...formData, voiceType: value })}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {voiceOptions.map((voice) => (
                              <SelectItem key={voice.value} value={voice.value}>
                                <div>
                                  <div className="font-medium">{voice.label}</div>
                                  <div className="text-xs text-gray-500">{voice.description}</div>
                                </div>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex items-end">
                        <Button variant="outline" size="sm" className="w-full bg-transparent">
                          <Volume2 className="w-4 h-4 mr-2" />
                          Preview Voice
                        </Button>
                      </div>
                      <div className="flex items-end">
                        <Button variant="outline" size="sm" className="w-full bg-transparent">
                          <Lightbulb className="w-4 h-4 mr-2" />
                          Script Tips
                        </Button>
                      </div>
                    </div>

                    <div>
                      <Label htmlFor="script" className="text-sm font-medium text-gray-700 mb-2 block">
                        Your Script or Notes
                      </Label>
                      <Textarea
                        id="script"
                        placeholder="Paste your podcast script here, or just write some notes. Our AI will help make it sound natural and engaging...

Example: 'Today I want to talk about my summer adventures. I visited three different countries and learned so much about myself along the way...'"
                        className="min-h-[200px] resize-none text-base leading-relaxed"
                        value={formData.scriptText}
                        onChange={(e) => setFormData({ ...formData, scriptText: e.target.value })} />
                      <div className="flex justify-between items-center mt-2">
                        <p className="text-xs text-gray-500">
                          {formData.scriptText.length} characters • Est. {Math.ceil(formData.scriptText.length / 150)}{" "}
                          minutes
                        </p>
                        <Button variant="ghost" size="sm" className="text-blue-600">
                          <Wand2 className="w-4 h-4 mr-1" />
                          Improve Script
                        </Button>
                      </div>
                    </div>

                    {isGenerating ? (
                      <div className="text-center space-y-4 py-8">
                        <div className="flex items-center justify-center space-x-3">
                          <RefreshCw className="w-6 h-6 animate-spin text-blue-600" />
                          <span className="text-lg font-medium text-blue-600">Generating your audio...</span>
                        </div>
                        <div className="max-w-md mx-auto">
                          <Progress value={66} className="h-2" />
                          <p className="text-sm text-gray-500 mt-2">This usually takes 30-60 seconds</p>
                        </div>
                      </div>
                    ) : generatedAudio ? (
                      <div className="text-center space-y-6 py-4">
                        <div className="flex items-center justify-center text-green-600">
                          <CheckCircle className="w-8 h-8 mr-3" />
                          <span className="text-xl font-semibold">Audio generated successfully!</span>
                        </div>

                        <Card className="max-w-md mx-auto" style={{ backgroundColor: "#ECF0F1" }}>
                          <CardContent className="p-6">
                            <div className="flex items-center space-x-4 mb-4">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setIsPlaying(!isPlaying)}
                                className="flex-shrink-0">
                                {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6" />}
                              </Button>
                              <div className="flex-1">
                                <div className="h-2 bg-gray-200 rounded-full mb-2">
                                  <div className="h-2 bg-blue-500 rounded-full w-1/3 transition-all"></div>
                                </div>
                                <div className="flex justify-between text-sm text-gray-600">
                                  <span>1:23</span>
                                  <span>4:23</span>
                                </div>
                              </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4 text-sm">
                              <div>
                                <div className="font-semibold text-gray-700">Voice</div>
                                <div className="text-gray-600 capitalize">{formData.voiceType}</div>
                              </div>
                              <div>
                                <div className="font-semibold text-gray-700">Quality</div>
                                <div className="text-green-600">Excellent</div>
                              </div>
                            </div>
                          </CardContent>
                        </Card>

                        <Button variant="outline" onClick={() => setGeneratedAudio(false)}>
                          <RefreshCw className="w-4 h-4 mr-2" />
                          Regenerate Audio
                        </Button>
                      </div>
                    ) : (
                      <Button
                        onClick={handleGenerateAudio}
                        disabled={!formData.scriptText.trim()}
                        size="lg"
                        className="w-full text-white py-4 text-lg"
                        style={{ backgroundColor: "#2C3E50" }}>
                        <Sparkles className="w-5 h-5 mr-3" />
                        Generate Professional Audio
                      </Button>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>

            <div className="text-center pt-8">
              <Button
                onClick={handleNextStep}
                disabled={!canProceedToStep2}
                size="lg"
                className="px-12 py-4 text-lg font-semibold text-white"
                style={{ backgroundColor: "#2C3E50" }}>
                Continue to Episode Details
                <ArrowLeft className="w-5 h-5 ml-2 rotate-180" />
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: Episode Details & Review */}
        {currentStep === 2 && (
          <div className="space-y-8">
            <div className="text-center mb-8">
              <h2 className="text-3xl font-bold mb-3" style={{ color: "#2C3E50" }}>
                Episode Details & Review
              </h2>
              <p className="text-gray-600 text-lg max-w-2xl mx-auto">
                Add episode information and configure your settings for the best results
              </p>
            </div>

            <div className="grid lg:grid-cols-3 gap-8">
              {/* Left Column - Episode Details */}
              <div className="lg:col-span-2 space-y-6">
                {/* AI Suggestions Card */}
                {aiSuggestions.title && (
                  <Card className="border-2 border-blue-200 bg-blue-50">
                    <CardHeader>
                      <CardTitle className="flex items-center text-blue-800">
                        <Zap className="w-5 h-5 mr-2" />
                        AI Suggestions
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div>
                        <div className="flex justify-between items-center mb-2">
                          <Label className="text-sm font-medium text-blue-800">Suggested Title</Label>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setFormData({ ...formData, episodeTitle: aiSuggestions.title })}
                            className="text-blue-600 hover:text-blue-800">
                            Use This
                          </Button>
                        </div>
                        <p className="text-sm text-blue-700 bg-white p-3 rounded border">{aiSuggestions.title}</p>
                      </div>
                      <div>
                        <div className="flex justify-between items-center mb-2">
                          <Label className="text-sm font-medium text-blue-800">Suggested Description</Label>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setFormData({ ...formData, episodeDescription: aiSuggestions.description })}
                            className="text-blue-600 hover:text-blue-800">
                            Use This
                          </Button>
                        </div>
                        <p
                          className="text-sm text-blue-700 bg-white p-3 rounded border line-clamp-3">
                          {aiSuggestions.description}
                        </p>
                      </div>
                      <div className="flex items-center space-x-4 text-sm">
                        <div className="flex items-center text-green-600">
                          <TrendingUp className="w-4 h-4 mr-1" />
                          Est. {aiSuggestions.estimatedListeners} listeners
                        </div>
                        <div className="flex items-center text-blue-600">
                          <Target className="w-4 h-4 mr-1" />
                          SEO Score: {aiSuggestions.seoScore}/100
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Episode Information */}
                <Card className="border-0 shadow-lg bg-white">
                  <CardHeader>
                    <CardTitle style={{ color: "#2C3E50" }}>Episode Information</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <EpisodeSegmentEditor
                      totalSeconds={totalSeconds}
                      segments={segments}
                      onChange={setSegments}
                    />
                    <div className="h-px bg-gray-200" />
                    <div>
                      <Label htmlFor="title" className="text-sm font-medium text-gray-700 mb-2 block">
                        Episode Title *
                      </Label>
                      <Input
                        id="title"
                        placeholder="e.g., My Summer Reflections"
                        className="text-base"
                        value={formData.episodeTitle}
                        onChange={(e) => setFormData({ ...formData, episodeTitle: e.target.value })} />
                      <p className="text-xs text-gray-500 mt-1">{formData.episodeTitle.length}/100 characters</p>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <Label htmlFor="description" className="text-sm font-medium text-gray-700">
                          Episode Description / Show Notes *
                        </Label>
                        <Button variant="ghost" size="sm" className="text-blue-600 hover:text-blue-800">
                          <Wand2 className="w-4 h-4 mr-1" />
                          Auto-Generate
                        </Button>
                      </div>
                      <Textarea
                        id="description"
                        placeholder="Describe what this episode is about, key topics covered, and any important notes for your listeners..."
                        className="min-h-[120px] resize-none text-base leading-relaxed"
                        value={formData.episodeDescription}
                        onChange={(e) => setFormData({ ...formData, episodeDescription: e.target.value })} />
                      <p className="text-xs text-gray-500 mt-1">{formData.episodeDescription.length}/500 characters</p>
                    </div>

                    <div className="grid md:grid-cols-2 gap-4">
                      <div>
                        <Label className="text-sm font-medium text-gray-700 mb-2 block">Category</Label>
                        <Select
                          value={formData.category}
                          onValueChange={(value) => setFormData({ ...formData, category: value })}>
                          <SelectTrigger>
                            <SelectValue placeholder="Select category" />
                          </SelectTrigger>
                          <SelectContent>
                            {categoryOptions.map((category) => (
                              <SelectItem key={category} value={category.toLowerCase()}>
                                {category}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="text-sm font-medium text-gray-700 mb-2 block">Tags</Label>
                        <div className="flex flex-wrap gap-2 mb-2">
                          {formData.tags.map((tag) => (
                            <Badge
                              key={tag}
                              variant="secondary"
                              className="cursor-pointer"
                              onClick={() => removeTag(tag)}>
                              {tag} ×
                            </Badge>
                          ))}
                        </div>
                        <Input
                          placeholder="Add tags (press Enter)"
                          onKeyPress={(e) => {
                            if (e.key === "Enter") {
                              addTag((e.target).value)
                              ;(e.target).value = ""
                            }
                          }} />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Right Column - Settings & Preview */}
              <div className="space-y-6">
                {/* Audio Preview */}
                <Card className="border-0 shadow-lg bg-white">
                  <CardHeader>
                    <CardTitle className="flex items-center" style={{ color: "#2C3E50" }}>
                      <Play className="w-5 h-5 mr-2" />
                      Audio Preview
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      <div className="flex items-center space-x-4 p-4 bg-gray-50 rounded-lg">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setIsPlaying(!isPlaying)}
                          className="flex-shrink-0">
                          {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6" />}
                        </Button>
                        <div className="flex-1">
                          <div className="flex items-center space-x-2 mb-1">
                            <div className="flex-1 h-2 bg-gray-200 rounded-full">
                              <div className="h-2 bg-blue-500 rounded-full w-1/4 transition-all"></div>
                            </div>
                            <span className="text-sm text-gray-600">{audioAnalysis.duration}</span>
                          </div>
                          <p className="text-xs text-gray-500">
                            {uploadedFile ? formatDisplayName(uploadedFile.name) : "Generated Audio"}
                          </p>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div className="bg-gray-50 p-3 rounded">
                          <div className="font-semibold text-gray-700">Quality</div>
                          <div className="text-green-600">{audioAnalysis.quality}</div>
                        </div>
                        <div className="bg-gray-50 p-3 rounded">
                          <div className="font-semibold text-gray-700">Loudness</div>
                          <div className="text-blue-600">{audioAnalysis.loudness}</div>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Audio Enhancement Settings */}
                <Card className="border-0 shadow-lg bg-white">
                  <CardHeader>
                    <CardTitle className="flex items-center" style={{ color: "#2C3E50" }}>
                      <Settings className="w-5 h-5 mr-2" />
                      Audio Enhancement
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <Label className="text-sm font-medium text-gray-700">Auto Enhancement</Label>
                        <p className="text-xs text-gray-500 mt-1">Improve sound quality and reduce noise</p>
                      </div>
                      <Switch
                        checked={formData.autoEnhancement}
                        onCheckedChange={(checked) => setFormData({ ...formData, autoEnhancement: checked })} />
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <Label className="text-sm font-medium text-gray-700">Remove Silences</Label>
                        <p className="text-xs text-gray-500 mt-1">Trim pauses longer than 3 seconds</p>
                      </div>
                      <Switch
                        checked={formData.removeSilences}
                        onCheckedChange={(checked) => setFormData({ ...formData, removeSilences: checked })} />
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <Label className="text-sm font-medium text-gray-700">Add Intro/Outro</Label>
                        <p className="text-xs text-gray-500 mt-1">Include branded intro and outro</p>
                      </div>
                      <Switch
                        checked={formData.addIntroOutro}
                        onCheckedChange={(checked) => setFormData({ ...formData, addIntroOutro: checked })} />
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <Label className="text-sm font-medium text-gray-700">Generate Chapters</Label>
                        <p className="text-xs text-gray-500 mt-1">Auto-create chapter markers</p>
                      </div>
                      <Switch
                        checked={formData.generateChapters}
                        onCheckedChange={(checked) => setFormData({ ...formData, generateChapters: checked })} />
                    </div>
                  </CardContent>
                </Card>

                {/* Performance Prediction */}
                <Card className="border-0 shadow-lg" style={{ backgroundColor: "#ECF0F1" }}>
                  <CardHeader>
                    <CardTitle className="flex items-center" style={{ color: "#2C3E50" }}>
                      <BarChart3 className="w-5 h-5 mr-2" />
                      Performance Prediction
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-600">Estimated Reach</span>
                      <span className="font-semibold" style={{ color: "#2C3E50" }}>
                        245 listeners
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-600">SEO Score</span>
                      <div className="flex items-center">
                        <span className="font-semibold text-green-600 mr-2">85/100</span>
                        <Star className="w-4 h-4 text-yellow-500" />
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-600">Engagement Score</span>
                      <span className="font-semibold text-blue-600">High</span>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>

            <div className="flex justify-between pt-8">
              <Button
                onClick={handlePreviousStep}
                variant="outline"
                size="lg"
                className="px-8 py-3 text-lg bg-transparent">
                <ArrowLeft className="w-5 h-5 mr-2" />
                Back
              </Button>
              <Button
                onClick={handleNextStep}
                disabled={!canProceedToStep3}
                size="lg"
                className="px-8 py-3 text-lg font-semibold text-white"
                style={{ backgroundColor: "#2C3E50" }}>
                Continue to Publish
                <ArrowLeft className="w-5 h-5 ml-2 rotate-180" />
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Publish / Schedule */}
        {currentStep === 3 && (
          <div className="space-y-8">
            <div className="text-center mb-8">
              <h2 className="text-3xl font-bold mb-3" style={{ color: "#2C3E50" }}>
                Publish Your Episode
              </h2>
              <p className="text-gray-600 text-lg max-w-2xl mx-auto">
                Choose when to make your episode available and configure additional options
              </p>
            </div>

            <div className="grid lg:grid-cols-3 gap-8">
              {/* Publishing Options */}
              <div className="lg:col-span-2">
                <Card className="border-0 shadow-lg bg-white">
                  <CardHeader>
                    <CardTitle style={{ color: "#2C3E50" }}>Publishing Options</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <RadioGroup
                      value={formData.publishOption}
                      onValueChange={(value) => setFormData({ ...formData, publishOption: value })}
                      className="space-y-6">
                      <div
                        className="flex items-center space-x-3 p-6 rounded-lg border-2 border-transparent hover:border-gray-200 transition-all">
                        <RadioGroupItem value="now" id="now" />
                        <div className="flex-1">
                          <Label
                            htmlFor="now"
                            className="text-xl font-medium cursor-pointer"
                            style={{ color: "#2C3E50" }}>
                            Publish Now
                          </Label>
                          <p className="text-gray-600 mt-2">
                            Your episode will be available immediately on all platforms
                          </p>
                          <div className="flex items-center space-x-4 mt-3 text-sm text-gray-500">
                            <div className="flex items-center">
                              <Globe className="w-4 h-4 mr-1" />
                              20+ platforms
                            </div>
                            <div className="flex items-center">
                              <Clock className="w-4 h-4 mr-1" />
                              Live in 5-10 minutes
                            </div>
                          </div>
                        </div>
                      </div>

                      <div
                        className="flex items-start space-x-3 p-6 rounded-lg border-2 border-transparent hover:border-gray-200 transition-all">
                        <RadioGroupItem value="schedule" id="schedule" className="mt-1" />
                        <div className="flex-1">
                          <Label
                            htmlFor="schedule"
                            className="text-xl font-medium cursor-pointer"
                            style={{ color: "#2C3E50" }}>
                            Schedule for Later
                          </Label>
                          <p className="text-gray-600 mt-2 mb-4">
                            Choose a specific date and time for your episode to go live
                          </p>

                          {formData.publishOption === "schedule" && (
                            <div className="grid sm:grid-cols-2 gap-4">
                              <div>
                                <Label htmlFor="date" className="text-sm font-medium text-gray-700 mb-2 block">
                                  Date
                                </Label>
                                <div className="relative">
                                  <Calendar
                                    className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                                  <Input
                                    id="date"
                                    type="date"
                                    className="pl-10"
                                    value={formData.scheduleDate}
                                    onChange={(e) => setFormData({ ...formData, scheduleDate: e.target.value })} />
                                </div>
                              </div>
                              <div>
                                <Label htmlFor="time" className="text-sm font-medium text-gray-700 mb-2 block">
                                  Time
                                </Label>
                                <div className="relative">
                                  <Clock
                                    className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                                  <Input
                                    id="time"
                                    type="time"
                                    className="pl-10"
                                    value={formData.scheduleTime}
                                    onChange={(e) => setFormData({ ...formData, scheduleTime: e.target.value })} />
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </RadioGroup>
                  </CardContent>
                </Card>

                {/* Additional Options */}
                <Card className="border-0 shadow-lg bg-white mt-6">
                  <CardHeader>
                    <CardTitle style={{ color: "#2C3E50" }}>Additional Options</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <Label className="text-sm font-medium text-gray-700">Generate Episode Artwork</Label>
                        <p className="text-xs text-gray-500 mt-1">Create custom artwork for this episode</p>
                      </div>
                      <Switch
                        checked={formData.generateArtwork}
                        onCheckedChange={(checked) => setFormData({ ...formData, generateArtwork: checked })} />
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <Label className="text-sm font-medium text-gray-700">Generate Social Media Posts</Label>
                        <p className="text-xs text-gray-500 mt-1">Auto-create promotional content</p>
                      </div>
                      <Switch
                        checked={formData.generateSocialPosts}
                        onCheckedChange={(checked) => setFormData({ ...formData, generateSocialPosts: checked })} />
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Episode Summary + Timeline */}
              <div className="space-y-6">
                <Card className="border-0 shadow-lg" style={{ backgroundColor: "#ECF0F1" }}>
                  <CardHeader>
                    <CardTitle style={{ color: "#2C3E50" }}>Episode Summary</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <Label className="text-sm font-medium text-gray-700">Title</Label>
                      <p className="text-sm text-gray-800 mt-1">{formData.episodeTitle || "Untitled Episode"}</p>
                    </div>
                    <div>
                      <Label className="text-sm font-medium text-gray-700">Duration</Label>
                      <p className="text-sm text-gray-800 mt-1">{audioAnalysis.duration}</p>
                    </div>
                    <div>
                      <Label className="text-sm font-medium text-gray-700">Category</Label>
                      <p className="text-sm text-gray-800 mt-1 capitalize">{formData.category || "Not selected"}</p>
                    </div>
                    <div>
                      <Label className="text-sm font-medium text-gray-700">Tags</Label>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {formData.tags.length > 0 ? (
                          formData.tags.map((tag) => (
                            <Badge key={tag} variant="secondary" className="text-xs">
                              {tag}
                            </Badge>
                          ))
                        ) : (
                          <p className="text-sm text-gray-500">No tags added</p>
                        )}
                      </div>
                    </div>
                    <div>
                      <Label className="text-sm font-medium text-gray-700">Enhancements</Label>
                      <div className="space-y-1 mt-1">
                        {formData.autoEnhancement && (
                          <div className="flex items-center text-xs text-green-600">
                            <CheckCircle className="w-3 h-3 mr-1" />
                            Audio enhancement
                          </div>
                        )}
                        {formData.removeSilences && (
                          <div className="flex items-center text-xs text-green-600">
                            <CheckCircle className="w-3 h-3 mr-1" />
                            Silence removal
                          </div>
                        )}
                        {formData.addIntroOutro && (
                          <div className="flex items-center text-xs text-green-600">
                            <CheckCircle className="w-3 h-3 mr-1" />
                            Intro/outro
                          </div>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-0 shadow-lg bg-white">
                  <CardHeader>
                    <CardTitle className="flex items-center" style={{ color: "#2C3E50" }}>
                      <MessageSquare className="w-5 h-5 mr-2" />
                      Quick Actions
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full justify-start bg-transparent">
                      <Eye className="w-4 h-4 mr-2" />
                      Preview Episode
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full justify-start bg-transparent">
                      <Download className="w-4 h-4 mr-2" />
                      Download Audio
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full justify-start bg-transparent">
                      <Share2 className="w-4 h-4 mr-2" />
                      Share Preview
                    </Button>
                  </CardContent>
                </Card>

                <EpisodePublishTimeline
                  publishOption={formData.publishOption}
                  scheduleDate={formData.scheduleDate}
                  scheduleTime={formData.scheduleTime}
                  durationText={audioAnalysis.duration}
                  hasArtwork={formData.generateArtwork}
                  hasSocial={formData.generateSocialPosts}
                />
                {segments && segments.length > 0 && (
                  <EpisodeStructureSummary
                    segments={segments}
                    totalSeconds={(audioAnalysis.duration.match(/^(\d+):(\d{1,2})$/) ? (parseInt(audioAnalysis.duration.split(':')[0])*60 + parseInt(audioAnalysis.duration.split(':')[1])) : 0) || 0}
                  />
                )}
              </div>
            </div>

            <div className="flex justify-between pt-8">
              <Button
                onClick={handlePreviousStep}
                variant="outline"
                size="lg"
                className="px-8 py-3 text-lg bg-transparent">
                <ArrowLeft className="w-5 h-5 mr-2" />
                Back
              </Button>
              <Button
                onClick={handlePublish}
                size="lg"
                className="px-12 py-4 text-xl font-semibold text-white"
                style={{ backgroundColor: "#2C3E50" }}>
                {formData.publishOption === "now" ? "🚀 Publish Episode" : "📅 Schedule Episode"}
              </Button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function CreatorUploadHint() {
  const [maxMb, setMaxMb] = React.useState(500);
  React.useEffect(() => {
    let canceled = false;
    (async () => {
      try {
        const res = await fetch('/api/public/config');
        const data = await res.json().catch(() => ({}));
        const n = parseInt(String(data?.max_upload_mb || '500'), 10);
        if (!canceled && isFinite(n) && !isNaN(n)) setMaxMb(Math.min(Math.max(n, 10), 2048));
      } catch {}
    })();
    return () => { canceled = true; };
  }, []);
  return (
    <div className="flex justify-center mt-4">
      <p className="text-sm text-gray-500 bg-gray-100 px-4 py-2 rounded-full">
        Supports MP3, WAV, M4A files up to {maxMb}MB
      </p>
    </div>
  );
}
