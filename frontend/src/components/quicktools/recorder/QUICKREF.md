# Recorder Architecture - Quick Reference

## Import Patterns

```javascript
// Use the full refactored component
import Recorder from '@/components/quicktools/RecorderRefactored';

// Import specific hooks for custom UIs
import { 
  useAudioGraph, 
  useDeviceSelection, 
  useMicCheck 
} from '@/components/quicktools/recorder';

// Import UI components for composition
import { 
  LevelMeter, 
  MicCheckOverlay 
} from '@/components/quicktools/recorder';

// Import utilities
import { 
  playBeep, 
  formatTime, 
  analyzeMicCheckLevels 
} from '@/components/quicktools/recorder';
```

---

## Hook Cheat Sheet

### `useDeviceSelection()`
```javascript
const { devices, selectedDeviceId, handleDeviceChange, ensurePermissionAndDevices } = useDeviceSelection();
// Auto-loads saved device from localStorage('ppp_selected_mic')
```

### `useAudioGraph({ peakLevelsRef })`
```javascript
const audioGraph = useAudioGraph({ peakLevelsRef });
// audioGraph.levelPct → 0-1 (current level)
// audioGraph.levelColor → '#22c55e' (green/yellow/red)
// audioGraph.inputGain → 0.1-2.0 (current gain)
// audioGraph.buildAudioGraph(stream) → Setup Web Audio
// audioGraph.updateGain(1.5) → Change gain (persists to localStorage)
```

### `useAudioRecorder({ buildAudioGraph, stopAudioGraph, toast })`
```javascript
const recorder = useAudioRecorder({ buildAudioGraph, stopAudioGraph, toast });
// recorder.isRecording → boolean
// recorder.audioBlob → Blob (after stop)
// recorder.handleRecordToggle(deviceId, onError) → Start/pause/resume
// recorder.reset() → Clear all state
```

### `useMicCheck({ audioGraph, deviceSelection, startStream, stopStream, onError })`
```javascript
const micCheck = useMicCheck({ audioGraph, deviceSelection, startStream, stopStream, onError });
// micCheck.handleMicCheck() → Run full flow (3-2-1, record, playback, analyze)
// micCheck.micCheckAnalysis → { status, message, suggestion, suggestedGain, requireRedo }
// micCheck.clearAnalysis() → Dismiss results
```

---

## Component Cheat Sheet

### `<LevelMeter />`
```javascript
<LevelMeter
  levelPct={0.65}              // 0-1
  levelColor="#22c55e"         // Hex color
  inputGain={1.2}              // 0.1-2.0
  onGainChange={(g) => {...}}  // Called on slider change
  showGainControl={true}       // Show/hide gain slider
/>
```

### `<DeviceSelector />`
```javascript
<DeviceSelector
  devices={[...]}              // Array of MediaDeviceInfo
  selectedDeviceId="abc123"    // Current device ID
  onDeviceChange={(id) => {}}  // Called on selection
  disabled={false}             // Disable during recording
/>
```

### `<RecorderControls />`
```javascript
<RecorderControls
  isRecording={true}
  isPaused={false}
  isCountingDown={false}
  countdown={3}
  elapsed={125}                // seconds
  onRecordToggle={() => {}}
  onStop={() => {}}
  onMicCheck={() => {}}
  micCheckCompleted={true}
  isMicChecking={false}
/>
```

---

## State Flow Diagrams

### Mic Check Flow
```
[Idle] → Click "Mic Check"
  ↓
[Countdown 3-2-1] (beeps)
  ↓
[Recording 5-4-3-2-1] (collecting peaks)
  ↓
[Playback] (user hears recording)
  ↓
[Analysis] → Good: Continue | Critical: Retry
  ↓
[Ready to Record]
```

### Recording Flow
```
[Ready] → Click "Start"
  ↓
[Countdown 3-2-1] (beeps)
  ↓
[Recording] → Click "Pause"
  ↓
[Paused] → Click "Resume"
  ↓
[Countdown 3-2-1] (beeps)
  ↓
[Recording] → Click "Pause"
  ↓
[Paused] → Click "Stop"
  ↓
[Preview] → Enter name → Click "Save"
  ↓
[Uploading] → Transcription polling
  ↓
[Done]
```

---

## LocalStorage Keys

```javascript
// Microphone selection
localStorage.getItem('ppp_selected_mic')      // Device ID string
localStorage.setItem('ppp_selected_mic', id)

// Input gain
localStorage.getItem('ppp_mic_gain')          // "1.2" (0.1-2.0)
localStorage.setItem('ppp_mic_gain', '1.5')
```

---

## Audio Analysis Thresholds

```javascript
// Raw audio levels (before 2.5x visual boost)
CRITICALLY_LOW = 0.05   // < 5% → Force redo
TOO_LOW = 0.15          // < 15% → Auto-boost
GOOD = 0.15-0.85        // 15-85% → Perfect!
TOO_HIGH = 0.85         // > 85% → Auto-reduce
CRITICALLY_HIGH = 0.95  // > 95% → Force redo
```

---

## Web Audio API Signal Chain

```
MediaStream (getUserMedia)
  ↓
GainNode (software volume control)
  ↓
AnalyserNode (level metering)
  ↓
MediaStreamDestination (for recording during mic check)
```

---

## Common Patterns

### Custom Recorder UI
```javascript
function MyCustomRecorder() {
  const devices = useDeviceSelection();
  const audioGraph = useAudioGraph();
  const recorder = useAudioRecorder({ 
    buildAudioGraph: audioGraph.buildAudioGraph,
    stopAudioGraph: audioGraph.stopAudioGraph,
    toast: useToast()
  });

  return (
    <div>
      <DeviceSelector {...devices} />
      <button onClick={() => recorder.handleRecordToggle(devices.selectedDeviceId)}>
        {recorder.isRecording ? 'Stop' : 'Start'}
      </button>
      <LevelMeter {...audioGraph} />
    </div>
  );
}
```

### Standalone Level Meter
```javascript
function AudioMonitor() {
  const audioGraph = useAudioGraph();
  
  useEffect(() => {
    // Get mic stream
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then(audioGraph.buildAudioGraph);
    
    return () => audioGraph.stopAudioGraph();
  }, []);

  return <LevelMeter {...audioGraph} showGainControl={false} />;
}
```

---

## Debugging Commands

```javascript
// In browser console:

// Check if audio graph is active
window._pppAudioCtx?.state  // "running" or "closed"

// Check current gain
window._pppGainNode?.gain.value  // 0.1-2.0

// Force stop audio graph
const hooks = React.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED;
// (Don't actually do this, use proper React DevTools)

// Check localStorage
localStorage.getItem('ppp_mic_gain')
localStorage.getItem('ppp_selected_mic')
```

---

## Error Handling

```javascript
// All hooks use consistent error pattern:
try {
  await someAudioOperation();
} catch (e) {
  if (e.name === 'NotAllowedError') {
    // User denied permission
  } else if (e.name === 'NotFoundError') {
    // No device found
  } else if (e.name === 'OverconstrainedError') {
    // Device doesn't support constraints
  } else {
    // Generic error
  }
}
```

---

## Performance Tips

1. **Don't build multiple audio graphs** - One per stream
2. **Always cleanup on unmount** - Prevents memory leaks
3. **Use refs for animation loops** - Not state updates
4. **Debounce gain changes** - Already done in hook
5. **Cleanup blob URLs** - `URL.revokeObjectURL(url)` when done

---

## Browser Compatibility

| Feature | Chrome | Firefox | Safari | Edge |
|---------|--------|---------|--------|------|
| MediaRecorder | ✅ | ✅ | ✅ | ✅ |
| Web Audio API | ✅ | ✅ | ✅ | ✅ |
| Wake Lock | ✅ | ❌ | ❌ | ✅ |
| Permissions API | ✅ | ✅ | ❌ | ✅ |

**Note:** All critical features work across browsers. Wake Lock and Permissions API are progressive enhancements.

---

## File Size Reference

```
useDeviceSelection.js    → 105 lines (~3 KB)
useAudioGraph.js         → 175 lines (~5 KB)
useAudioRecorder.js      → 380 lines (~11 KB)
useMicCheck.js           → 195 lines (~6 KB)
audioUtils.js            → 200 lines (~6 KB)
audioAnalysis.js         → 80 lines (~2 KB)
Total hooks + utils      → ~33 KB uncompressed
                          → ~8 KB gzipped
```

---

**Last Updated:** October 22, 2025  
**Maintainer:** AI Agent (Claude)  
**Questions?** Check `recorder/README.md` for full documentation
