import { useState, useRef, useCallback, useEffect } from 'react';

/**
 * Hook for managing audio device selection and permissions
 * @returns {Object} Device selection state and functions
 */
export const useDeviceSelection = () => {
  const [devices, setDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [supportError, setSupportError] = useState("");
  const isRequestingDevicesRef = useRef(false);

  // Load saved device from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem("ppp_selected_mic");
      if (saved) {
        setSelectedDeviceId(saved);
      }
    } catch {}
  }, []);

  /**
   * Ensure microphone permission and enumerate devices
   */
  const ensurePermissionAndDevices = useCallback(async () => {
    // Prevent concurrent requests
    if (isRequestingDevicesRef.current) {
      console.log("[DeviceSelection] Already requesting devices, skipping...");
      return { success: false, reason: 'already_requesting' };
    }

    try {
      isRequestingDevicesRef.current = true;
      
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setSupportError("Your browser does not support audio recording.");
        return { success: false, reason: 'not_supported' };
      }

      // Request permission first
      console.log("[DeviceSelection] Requesting microphone permission...");
      const tempStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Stop the temp stream immediately
      tempStream.getTracks().forEach((t) => t.stop());

      // Now enumerate devices
      console.log("[DeviceSelection] Enumerating audio devices...");
      const allDevices = await navigator.mediaDevices.enumerateDevices();
      const audioInputs = allDevices.filter((d) => d.kind === "audioinput");

      if (audioInputs.length === 0) {
        setSupportError("No microphone found. Please connect a microphone.");
        return { success: false, reason: 'no_devices' };
      }

      console.log(`[DeviceSelection] Found ${audioInputs.length} audio input device(s)`);
      setDevices(audioInputs);
      setSupportError("");

      // Auto-select first device if none selected
      if (!selectedDeviceId && audioInputs.length > 0) {
        const firstId = audioInputs[0].deviceId;
        setSelectedDeviceId(firstId);
        try {
          localStorage.setItem("ppp_selected_mic", firstId);
        } catch {}
        console.log("[DeviceSelection] Auto-selected first device:", audioInputs[0].label || firstId);
      }

      return { success: true, devices: audioInputs };
    } catch (err) {
      console.error("[DeviceSelection] Error:", err);
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        setSupportError("Microphone permission denied. Please allow access and try again.");
        return { success: false, reason: 'permission_denied' };
      } else {
        setSupportError(`Error accessing microphone: ${err.message}`);
        return { success: false, reason: 'error', error: err };
      }
    } finally {
      isRequestingDevicesRef.current = false;
    }
  }, [selectedDeviceId]);

  /**
   * Handle device selection change
   */
  const handleDeviceChange = useCallback((deviceId) => {
    setSelectedDeviceId(deviceId);
    try {
      localStorage.setItem("ppp_selected_mic", deviceId);
    } catch {}
    console.log("[DeviceSelection] Device changed to:", deviceId);
  }, []);

  return {
    devices,
    selectedDeviceId,
    supportError,
    ensurePermissionAndDevices,
    handleDeviceChange,
    setSelectedDeviceId, // For backward compatibility
  };
};
