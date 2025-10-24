/**
 * Analyze microphone check audio levels and provide feedback
 * SIMPLIFIED LOGIC - No complex thresholds, just 3 states: silent, clipping, or good
 * @param {number[]} peakLevels - Array of raw peak audio levels (0-1 range)
 * @param {number} currentGain - Current gain multiplier (unused, kept for API compatibility)
 * @returns {Object} Analysis results with status, message, suggestion, and recommendations
 */
export const analyzeMicCheckLevels = (peakLevels, currentGain) => {
  // Count how many samples show meaningful audio activity
  const avg = peakLevels.reduce((a, b) => a + b, 0) / peakLevels.length;
  const max = Math.max(...peakLevels);
  
  // Count samples above various thresholds
  const samplesAbove5 = peakLevels.filter(p => p > 0.05).length;
  const samplesAbove10 = peakLevels.filter(p => p > 0.10).length;
  const samplesAbove50 = peakLevels.filter(p => p > 0.50).length;
  
  console.log('[MicCheck Analysis] Avg:', avg.toFixed(3), 'Max:', max.toFixed(3), 
              'Samples >5%:', samplesAbove5, '>10%:', samplesAbove10, '>50%:', samplesAbove50);
  
  let status = 'good';
  let message = '';
  let suggestion = '';
  let suggestedGain = currentGain;
  let requireRedo = false;
  
  // CRITICAL: Check for actual speech/audio content
  // During a 5-second mic check, we expect substantial audio activity when user is speaking
  // Silence detection: Very low max OR very few active samples
  if (max < 0.08 || samplesAbove10 < 20) {
    status = 'silent';
    message = '🔇 No audio detected';
    suggestion = 'Your microphone appears to be muted or you didn\'t speak during the test.\n\n• Check Windows Sound Settings\n• Make sure the microphone isn\'t muted\n• Speak at normal volume during the mic check\n• Try unplugging and replugging the mic';
    requireRedo = true;
  } 
  // Too quiet: Some audio but consistently very low (needs to be MUCH louder)
  else if (max < 0.20 || (avg < 0.08 && samplesAbove10 < 50)) {
    status = 'too_quiet';
    message = '🔉 Microphone is too quiet';
    suggestion = 'We can barely hear you.\n\n• In Windows Sound Settings, increase microphone volume to 70-80%\n• Speak closer to the microphone\n• Make sure you\'re using the right microphone input\n• Speak louder and more clearly';
    requireRedo = true;
  }
  // Clipping: Too many samples hitting the ceiling
  else if (samplesAbove50 > peakLevels.length * 0.3 || max > 0.95) {
    status = 'clipping';
    message = '⚠️ Audio is too loud (distorting)';
    suggestion = 'Your audio is clipping and will sound distorted.\n\n• In Windows Sound Settings, reduce microphone volume to 40-60%\n• Move back from the microphone\n• Speak a bit more softly';
    requireRedo = true;
  }
  // Good: Audio is present and reasonable
  else {
    status = 'good';
    message = '✅ Microphone is working!';
    suggestion = 'We can hear you clearly. You\'re ready to start recording.\n\nThe audio will be professionally processed and optimized when you finish your episode.';
  }
  
  return {
    status,
    message,
    suggestion,
    suggestedGain,
    requireRedo,
    stats: { avg, max, min: Math.min(...peakLevels) }
  };
};
