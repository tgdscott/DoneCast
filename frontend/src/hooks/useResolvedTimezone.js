import { useMemo } from 'react';
import { useAuth } from '@/AuthContext';
import { detectDeviceTimezone, resolveUserTimezone } from '@/lib/timezone';

export const useResolvedTimezone = (preferredTimezone = null) => {
  const { user } = useAuth() || {};
  const deviceTimezone = useMemo(() => detectDeviceTimezone(), []);
  return useMemo(
    () => resolveUserTimezone(preferredTimezone, user?.timezone, deviceTimezone),
    [preferredTimezone, user?.timezone, deviceTimezone]
  );
};
