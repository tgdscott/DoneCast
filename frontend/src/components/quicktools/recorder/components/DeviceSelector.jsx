import React from 'react';
import { Label } from "@/components/ui/label";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";

/**
 * Microphone device selector
 * @param {Object} props - Component props
 * @param {Array} props.devices - Array of audio input devices
 * @param {string} props.selectedDeviceId - Currently selected device ID
 * @param {Function} props.onDeviceChange - Callback when device changes
 * @param {boolean} [props.disabled=false] - Whether the selector is disabled
 */
export const DeviceSelector = ({
  devices,
  selectedDeviceId,
  onDeviceChange,
  disabled = false
}) => {
  if (!devices || devices.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      <Label htmlFor="mic-device" className="text-base font-medium">
        Microphone
      </Label>
      <Select
        value={selectedDeviceId}
        onValueChange={onDeviceChange}
        disabled={disabled}
      >
        <SelectTrigger id="mic-device" className="w-full">
          <SelectValue placeholder="Select a microphone" />
        </SelectTrigger>
        <SelectContent>
          {devices.map((d) => (
            <SelectItem key={d.deviceId} value={d.deviceId}>
              {d.label || `Microphone ${d.deviceId.substring(0, 8)}...`}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
};
