# Recorder Component - Refactored Architecture

## Overview
Browser-based podcast recording interface with intelligent microphone check, real-time level metering, and automatic gain control.

**Refactored:** October 22, 2025  
**Lines Reduced:** 1,741 → ~300 (main component)  
**Structure:** Modular hooks + composable UI components

---

## Directory Structure

```
recorder/
├── hooks/
│   ├── useDeviceSelection.js      # Microphone device enumeration & permission
│   ├── useAudioGraph.js           # Web Audio API (analyser, gain, level metering)
│   ├── useAudioRecorder.js        # MediaRecorder lifecycle & state
│   └── useMicCheck.js             # Mic check orchestration & analysis
├── components/
│   ├── DeviceSelector.jsx         # Microphone dropdown
│   ├── LevelMeter.jsx             # Audio level meter with gain control
│   ├── MicCheckOverlay.jsx        # Full-screen mic check UI
│   ├── RecorderControls.jsx       # Record/Pause/Stop buttons
│   └── RecordingPreview.jsx       # Playback & save UI
├── utils/
│   ├── audioUtils.js              # Pure functions (beep, format, WAV encoding)
│   └── audioAnalysis.js           # Mic check level analysis logic
└── index.js                       # Public exports

RecorderRefactored.jsx             # Main orchestrator component (300 lines)
```

---

## Architecture Principles

### 1. **Separation of Concerns**
- **Hooks** = Business logic (stateful, side effects)
- **Components** = Presentation (pure UI, minimal logic)
- **Utils** = Pure functions (no state, no side effects)

### 2. **Single Responsibility**
Each file has ONE clear purpose:
- `useAudioGraph` ONLY handles Web Audio API
- `LevelMeter` ONLY renders the level bar
- `audioAnalysis.js` ONLY analyzes audio levels

### 3. **Composability**
Hooks and components can be used independently:
```javascript
// Use just the level meter in another component
import { LevelMeter } from '@/components/quicktools/recorder';

// Use just device selection elsewhere
import { useDeviceSelection } from '@/components/quicktools/recorder';
```

---

## Hook APIs

### `useDeviceSelection()`
**Purpose:** Manage microphone device enumeration and selection  
**Returns:**
```javascript
{
  devices: Array<MediaDeviceInfo>,
  selectedDeviceId: string,
  supportError: string,
  ensurePermissionAndDevices: () => Promise<{success, reason}>,
  handleDeviceChange: (deviceId) => void
}
```
**LocalStorage:** Persists `ppp_selected_mic`

---

### `useAudioGraph({ peakLevelsRef })`
**Purpose:** Real-time audio level metering with gain control  
**Returns:**
```javascript
{
  levelPct: number (0-1),
  levelColor: string (hex color),
  inputGain: number (0.1-2.0),
  buildAudioGraph: (stream) => void,
  stopAudioGraph: () => void,
  updateGain: (newGain) => void,
  audioCtxRef, analyserRef, sourceRef, gainNodeRef  // For advanced use
}
```
**Features:**
- 2.5x visual boost (40% raw → 100% display)
- Exponential smoothing for smooth animations
- Color zones: red < 30% < yellow < 50% < green < 85% < yellow < 95% < red
- CSS transitions for jank-free UX
**LocalStorage:** Persists `ppp_mic_gain`

---

### `useAudioRecorder({ buildAudioGraph, stopAudioGraph, toast })`
**Purpose:** MediaRecorder state machine with countdown and wake lock  
**Returns:**
```javascript
{
  // State
  isRecording, isPaused, hasPreview, elapsed,
  audioUrl, audioBlob, mimeType,
  isCountingDown, countdown,
  
  // Refs
  streamRef,
  
  // Functions
  startRecording: (deviceId, onError) => Promise<void>,
  stopRecording: () => void,
  pauseRecording: () => void,
  handleRecordToggle: (deviceId, onError) => void,
  handleStop: () => void,
  startCountdown: (callback) => void,
  cancelCountdown: () => void,
  reset: () => void
}
```
**Features:**
- 3-second countdown before recording (with beeps)
- Pause/resume with countdown
- Auto WAV re-encoding to fix browser quirks
- Screen wake lock during recording
- 30-second minimum for "stop" protection

---

### `useMicCheck({ audioGraph, deviceSelection, startStream, stopStream, onError })`
**Purpose:** Orchestrate mic check flow with intelligent analysis  
**Returns:**
```javascript
{
  // State
  isMicChecking, micCheckCountdown, micCheckPlayback,
  micCheckCompleted, micCheckAnalysis,
  
  // Refs
  peakLevelsRef,
  
  // Functions
  handleMicCheck: () => Promise<void>,
  clearAnalysis: () => void,
  resetMicCheck: () => void
}
```
**Flow:**
1. 3-2-1 countdown (pre-check)
2. 5-second recording with countdown
3. Playback for user confirmation
4. Analysis with thresholds:
   - **Critical low:** < 5% (force redo)
   - **Too low:** < 15% (auto-adjust gain)
   - **Good:** 15-85% (perfect!)
   - **Too high:** > 85% (auto-adjust gain)
   - **Critical high:** > 95% (force redo)
5. Auto-apply gain or show redo button

---

## Component APIs

### `<DeviceSelector />`
**Props:** `devices`, `selectedDeviceId`, `onDeviceChange`, `disabled`  
**Purpose:** Dropdown for selecting microphone

---

### `<LevelMeter />`
**Props:** `levelPct`, `levelColor`, `inputGain`, `onGainChange`, `showGainControl`  
**Purpose:** Visual audio level bar with optional gain slider  
**Features:**
- Color-coded zones
- Real-time percentage display
- Software gain control (10%-200%)
- Guidance text explaining system vs. software volume

---

### `<MicCheckOverlay />`
**Props:** `isVisible`, `countdown`, `isPlayback`, `analysis`, `levelPct`, `levelColor`, `inputGain`, `onGainChange`, `onContinue`, `onRetry`  
**Purpose:** Full-screen modal for mic check flow  
**States:**
- Pre-check countdown (3-2-1)
- Recording countdown (5-4-3-2-1)
- Playback (spinner)
- Analysis results (color-coded panel)

---

### `<RecorderControls />`
**Props:** `isRecording`, `isPaused`, `isCountingDown`, `countdown`, `elapsed`, `onRecordToggle`, `onStop`, `onMicCheck`, `micCheckCompleted`, `isMicChecking`  
**Purpose:** Primary recording action buttons  
**Features:**
- "Do Mic Check First" button (before first recording)
- Record/Pause/Resume/Stop logic
- Timer display
- "Run Mic Check Again" button (secondary)

---

### `<RecordingPreview />`
**Props:** `audioUrl`, `audioBlob`, `recordingName`, `onNameChange`, `onSave`, `isSaving`, `savedDisplayName`, `transcriptReady`, `showTimeoutNotice`, `maxUploadMb`, `onFinish`  
**Purpose:** Audio playback, naming, and upload UI  
**Features:**
- HTML5 audio player
- File size validation
- Transcription polling status
- "Done" button after save

---

## Utility Functions

### `audioUtils.js`
- `playBeep(frequency, duration)` - Web Audio beep sound
- `formatTime(seconds)` - MM:SS formatter
- `pickMimeType()` - Best codec for browser
- `reencodeToWav(blob)` - PCM WAV re-encoding
- `extractStemFromFilename(filename)` - Remove extension
- `ensureExt(name, ext)` - Add extension if missing
- `formatDateName()` - Timestamp-based filename
- `isMobileDevice()` - User agent detection

### `audioAnalysis.js`
- `analyzeMicCheckLevels(peakLevels, currentGain)` - Analyze audio and return guidance

---

## Data Flow

```
User Action → Hook (business logic) → Component (UI update)
                ↓
            LocalStorage / API
```

**Example: Gain Adjustment**
1. User drags slider → `<LevelMeter />` calls `onGainChange`
2. `useAudioGraph` receives `updateGain(newValue)`
3. Hook updates `gainNodeRef.current.gain.value` (Web Audio)
4. Hook persists to `localStorage.setItem('ppp_mic_gain', ...)`
5. Hook updates state `setInputGain(newValue)`
6. React re-renders `<LevelMeter />` with new value

---

## Testing Strategy

### Unit Tests (Hooks)
```javascript
import { renderHook, act } from '@testing-library/react-hooks';
import { useAudioGraph } from './useAudioGraph';

test('updateGain clamps to 0.1-2.0 range', () => {
  const { result } = renderHook(() => useAudioGraph());
  act(() => result.current.updateGain(5.0));
  expect(result.current.inputGain).toBe(2.0);
});
```

### Component Tests
```javascript
import { render, screen } from '@testing-library/react';
import { LevelMeter } from './LevelMeter';

test('shows percentage text', () => {
  render(<LevelMeter levelPct={0.65} levelColor="#22c55e" inputGain={1.0} onGainChange={() => {}} />);
  expect(screen.getByText('65%')).toBeInTheDocument();
});
```

---

## Migration Notes

### From Old `Recorder.jsx` to Refactored
**Breaking Changes:** None - API is backward compatible  
**Import Change:**
```javascript
// Old
import Recorder from '@/components/quicktools/Recorder';

// New (both work, but prefer new path)
import Recorder from '@/components/quicktools/RecorderRefactored';
// OR
import { Recorder } from '@/components/quicktools/recorder';
```

### Gradual Migration Path
1. Keep `Recorder.jsx` (old) as fallback
2. Use `RecorderRefactored.jsx` in new contexts
3. Test production for 1 week
4. Delete `Recorder.jsx` and rename `RecorderRefactored` → `Recorder`

---

## Performance Considerations

### Audio Graph Optimization
- Uses `requestAnimationFrame` (not timers) for level updates
- Samples every 10th frame to reduce peak array size
- Updates color every 30 frames (~0.5s) for stability
- CSS transitions offload animation to GPU

### Memory Management
- Cleans up `AudioContext` on unmount
- Revokes blob URLs after use
- Cancels animation frames
- Clears intervals

---

## Future Enhancements

### Phase 2 (Potential)
- [ ] Multi-track recording (interview mode)
- [ ] Visual waveform display
- [ ] Automatic silence detection
- [ ] Cloud auto-save (draft recovery)
- [ ] Mobile-optimized UI (touch gestures)

### Hooks to Extract Later
- `useTranscriptionPolling` (currently inline)
- `useKeyboardShortcuts` (currently inline)
- `useWakeLock` (currently in useAudioRecorder)

---

## Troubleshooting

### "Mic check stuck in countdown"
**Cause:** `buildAudioGraph` failed silently  
**Fix:** Check console for Web Audio API errors, ensure HTTPS

### "Levels not moving"
**Cause:** `analyserRef.current` is null  
**Fix:** Ensure `buildAudioGraph` succeeded before calling `buildAudioGraph`

### "Gain not persisting"
**Cause:** LocalStorage blocked (private browsing)  
**Fix:** Wrap in try/catch (already done)

---

## Credits
**Original Author:** (Monolithic 1,741-line component)  
**Refactored By:** AI Agent (Claude)  
**Date:** October 22, 2025  
**Principle:** "A component should do ONE thing well, not ALL things poorly"
