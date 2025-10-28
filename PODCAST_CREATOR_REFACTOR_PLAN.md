# Podcast Creator Hook Refactoring Plan

## Current State
- **File:** `frontend/src/components/dashboard/hooks/usePodcastCreator.js`
- **Size:** 2,273 lines
- **Complexity:** 10 distinct state domains, 90+ state variables, 33 useEffect blocks, 27 handler functions

## Problem Statement
The `usePodcastCreator` hook has become a monolithic "god hook" that manages the entire podcast creation workflow. This creates:
- **Difficult maintenance** - changes in one area risk breaking unrelated features
- **Hard to test** - testing individual features requires mocking the entire hook
- **Cognitive overload** - developers must understand all 10 domains to make changes
- **Poor reusability** - smaller features can't be extracted for use elsewhere

## Strategy: Vertical Slice Extraction
Unlike the admin dashboard (which had natural tab boundaries), this hook requires **vertical slicing** - each extracted hook handles a complete feature domain with its own:
- State variables
- Handler functions  
- useEffect blocks
- Return values (exposed state + handlers)

## 10 State Domains Identified

### 1. Step Navigation (Priority: HIGH)
**Lines:** ~14-30, handlers at ~911  
**State:** currentStep, selectedTemplate, progressPercentage, steps[]  
**Handlers:** handleTemplateSelect (1)  
**Extract to:** `useStepNavigation.js` (~200 lines)  
**Rationale:** Foundation for all other features - extract first

### 2. File Upload (Priority: HIGH)
**Lines:** ~20-40, handlers at ~947-1070  
**State:** uploadedFile, uploadedFilename, wasRecorded, isUploading, uploadProgress, uploadStats, fileInputRef, uploadXhrRef  
**Handlers:** handleFileChange, handlePreuploadedSelect, cancelBuild (5)  
**Extract to:** `useFileUpload.js` (~350 lines)  
**Rationale:** Self-contained, critical path feature

### 3. Assembly/Processing (Priority: HIGH)
**Lines:** ~40-60, handlers at ~1395-1550  
**State:** isAssembling, assemblyComplete, assembledEpisode, jobId, statusMessage, error, audioDurationSec, processingEstimate  
**Handlers:** handleAssemble (1)  
**useEffect blocks:** Assembly status polling, completion triggers  
**Extract to:** `useEpisodeAssembly.js` (~400 lines)  
**Rationale:** Core workflow orchestration, many side effects

### 4. TTS/Voice Configuration (Priority: MEDIUM)
**Lines:** ~50-70, handlers at ~469, 1196  
**State:** ttsValues, showVoicePicker, voicePickerTargetId, voiceNameById, voicesLoading  
**Handlers:** handleVoiceChange, handleTtsChange (2)  
**Extract to:** `useVoiceConfiguration.js` (~250 lines)  
**Rationale:** Isolated TTS/ElevenLabs integration

### 5. AI Features - Flubber & Intern (Priority: MEDIUM)
**Lines:** ~60-90, handlers at ~1552-1850  
**State:** flubberContexts, showFlubberReview, flubberNotFound, internReviewContexts, showInternReview, internResponses  
**Handlers:** handleFlubberConfirm, handleFlubberCancel, handleInternComplete, handleInternCancel, retryFlubberSearch, skipFlubberRetry (6)  
**Extract to:** `useAIFeatures.js` (~450 lines)  
**Rationale:** Self-contained AI processing workflows

### 6. Intent Detection (Priority: LOW)
**Lines:** ~70-90, handlers at ~415, 1650-1750  
**State:** intents, intentDetections, intentDetectionReady, intentVisibility, intentsComplete, pendingIntentLabels, showIntentQuestions  
**Handlers:** handleIntentSubmit, handleIntentAnswerChange (2)  
**Extract to:** `useIntentDetection.js` (~300 lines)  
**Rationale:** Could merge with AI Features, but distinct enough for separation

### 7. Episode Metadata (Priority: MEDIUM)
**Lines:** ~70-90, handlers at ~1200, 1319-1390  
**State:** episodeDetails, isAiTitleBusy, isAiDescBusy, missingTitle, missingEpisodeNumber  
**Handlers:** handleDetailsChange, handleAISuggestTitle, handleAIRefineTitle, handleAISuggestDescription, handleAIRefineDescription (5)  
**Extract to:** `useEpisodeMetadata.js` (~350 lines)  
**Rationale:** AI suggestion logic is complex, needs isolation

### 8. Publishing Workflow (Priority: MEDIUM)
**Lines:** ~80-100, handlers at ~1850-1990  
**State:** publishMode, publishVisibility, scheduleDate, scheduleTime, autoPublishPending, isPublishing  
**Handlers:** handlePublish (1)  
**useEffect blocks:** Auto-publish trigger on assembly complete  
**Extract to:** `usePublishing.js` (~300 lines)  
**Rationale:** Critical side effects, needs careful extraction

### 9. Cover Art Management (Priority: LOW)
**Lines:** ~50-70, handlers at ~1115-1195  
**State:** coverArtInputRef, coverCropperRef, isUploadingCover, coverNeedsUpload, coverMode  
**Handlers:** uploadCover, handleCoverFileSelected, handleUploadProcessedCover, clearCover, updateCoverCrop (5)  
**Extract to:** `useCoverArtManagement.js` (~250 lines)  
**Rationale:** Isolated feature, low coupling

### 10. Quota/Usage Tracking (Priority: LOW)
**Lines:** ~80-100, handlers at ~2040-2100  
**State:** usage, quotaInfo, capabilities, minutesRemaining, minutesCap, minutesBlocking, minutesPrecheck, minutesPrecheckPending, minutesPrecheckError, minutesDialog  
**Handlers:** refreshUsage, retryMinutesPrecheck (2)  
**Extract to:** `useQuotaTracking.js` (~200 lines)  
**Rationale:** Self-contained billing/limits logic

---

## Execution Phases

### Phase 1: Foundation Hooks (HIGH Priority)
**Target: ~950 lines reduction**

1. ✅ **Extract useStepNavigation** (~200 lines)
   - State: currentStep, selectedTemplate, progressPercentage, steps
   - Handlers: handleTemplateSelect, setCurrentStep
   - Dependencies: None (pure navigation logic)
   
2. ✅ **Extract useFileUpload** (~350 lines)
   - State: uploadedFile, uploadedFilename, isUploading, uploadProgress, etc.
   - Handlers: handleFileChange, handlePreuploadedSelect, cancelBuild
   - Dependencies: useStepNavigation (to advance step on upload complete)
   
3. ✅ **Extract useEpisodeAssembly** (~400 lines)
   - State: isAssembling, assemblyComplete, assembledEpisode, jobId, etc.
   - Handlers: handleAssemble
   - Dependencies: useFileUpload (uploadedFilename), useStepNavigation (currentStep)

**Validation:** After Phase 1, main hook should be ~1,323 lines

---

### Phase 2: Feature-Specific Hooks (MEDIUM Priority)
**Target: ~800 lines reduction**

4. ✅ **Extract useVoiceConfiguration** (~250 lines)
   - State: ttsValues, voiceNameById, voicesLoading
   - Handlers: handleVoiceChange, handleTtsChange
   
5. ✅ **Extract useEpisodeMetadata** (~350 lines)
   - State: episodeDetails, AI title/desc busy states
   - Handlers: handleDetailsChange, AI suggest/refine functions
   
6. ✅ **Extract usePublishing** (~300 lines)
   - State: publishMode, scheduleDate/Time, autoPublishPending
   - Handlers: handlePublish
   - Dependencies: useEpisodeAssembly (assembledEpisode)

**Validation:** After Phase 2, main hook should be ~523 lines

---

### Phase 3: Optional Feature Hooks (LOW Priority)
**Target: ~450 lines reduction**

7. ✅ **Extract useAIFeatures** (~450 lines)
   - State: flubberContexts, internReviewContexts
   - Handlers: handleFlubberConfirm/Cancel, handleInternComplete/Cancel
   - Could be split further into `useFlubber` + `useIntern`

**Validation:** After Phase 3, main hook should be ~73 lines (orchestration only)

---

### Phase 4: Utility Hooks (if needed)
**Target: ~450 lines reduction**

8. ✅ **Extract useIntentDetection** (~300 lines)
9. ✅ **Extract useCoverArtManagement** (~250 lines)
10. ✅ **Extract useQuotaTracking** (~200 lines)

**Final State:** Main hook becomes ~73-line orchestrator that composes all sub-hooks

---

## New File Structure
```
frontend/src/components/dashboard/hooks/
├── usePodcastCreator.js          # Main orchestrator (~73 lines after refactor)
├── creator/
│   ├── useStepNavigation.js      # ~200 lines
│   ├── useFileUpload.js          # ~350 lines
│   ├── useEpisodeAssembly.js     # ~400 lines
│   ├── useVoiceConfiguration.js  # ~250 lines
│   ├── useEpisodeMetadata.js     # ~350 lines
│   ├── usePublishing.js          # ~300 lines
│   ├── useAIFeatures.js          # ~450 lines (or split to useFlubber + useIntern)
│   ├── useIntentDetection.js     # ~300 lines
│   ├── useCoverArtManagement.js  # ~250 lines
│   └── useQuotaTracking.js       # ~200 lines
```

---

## Risks & Mitigation

### Risk 1: Tight Coupling Between Hooks
**Problem:** Many features depend on each other (e.g., assembly needs upload filename, publish needs assembled episode)  
**Mitigation:** Pass dependencies explicitly via hook parameters, use context for shared state if needed

### Risk 2: Breaking Existing Components
**Problem:** PodcastCreator component expects specific return shape from hook  
**Mitigation:** Keep return shape identical - main orchestrator hook re-exports all sub-hook values

### Risk 3: useEffect Dependency Chains
**Problem:** Complex useEffect blocks that span multiple domains  
**Mitigation:** Extract cross-cutting effects to main orchestrator, keep domain-specific effects in sub-hooks

### Risk 4: Testing Complexity
**Problem:** Testing sub-hooks in isolation may not catch integration bugs  
**Mitigation:** Keep integration tests for main hook, add unit tests for sub-hooks

---

## Success Metrics

✅ **Line count reduction:** 2,273 → ~73 lines (96.7% reduction in main file)  
✅ **Modularity:** 10 focused hooks, each <450 lines  
✅ **Testability:** Each sub-hook testable in isolation  
✅ **Maintainability:** Changes to one feature don't require understanding others  
✅ **Zero regressions:** All existing functionality preserved  

---

## Next Steps

1. **Review this plan** - Confirm extraction strategy with team
2. **Start Phase 1** - Extract useStepNavigation first (smallest, no dependencies)
3. **Validate incrementally** - Test after each extraction
4. **Commit frequently** - One commit per extracted hook
5. **Update documentation** - Document hook composition pattern

---

*Plan created: 2024-01-XX*  
*Status: PENDING APPROVAL*
