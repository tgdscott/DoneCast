// Main Recorder Component
export { default as Recorder } from './RecorderRefactored';

// Hooks
export { useDeviceSelection } from './recorder/hooks/useDeviceSelection';
export { useAudioGraph } from './recorder/hooks/useAudioGraph';
export { useAudioRecorder } from './recorder/hooks/useAudioRecorder';
export { useMicCheck } from './recorder/hooks/useMicCheck';

// Components
export { DeviceSelector } from './recorder/components/DeviceSelector';
export { LevelMeter } from './recorder/components/LevelMeter';
export { MicCheckOverlay } from './recorder/components/MicCheckOverlay';
export { RecorderControls } from './recorder/components/RecorderControls';
export { RecordingPreview } from './recorder/components/RecordingPreview';

// Utils
export * from './recorder/utils/audioUtils';
export { analyzeMicCheckLevels } from './recorder/utils/audioAnalysis';
