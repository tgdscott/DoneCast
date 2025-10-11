import React, { useEffect, useState } from 'react';
import { useAuth } from '@/AuthContext';
import { makeApi } from '@/lib/apiClient';

export default function BuildInfo() {
    const { user, token } = useAuth();
    const [buildInfo, setBuildInfo] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!user?.is_admin || !token) return;

        const fetchBuildInfo = async () => {
            try {
                const api = makeApi(token);
                const data = await api.get('/api/admin/build-info');
                setBuildInfo(data);
                setError(null);
            } catch (err) {
                setError(err.message);
            }
        };

        // Fetch immediately
        fetchBuildInfo();

        // Then fetch every 30 seconds
        const interval = setInterval(fetchBuildInfo, 30000);
        return () => clearInterval(interval);
    }, [user, token]);

    // Only show for admin users
    if (!user?.is_admin) return null;
    if (error) return null; // Silent fail if endpoint not available yet

    if (!buildInfo) return null;

    // Extract revision number (e.g., "podcast-api-00506-zb9" -> "506")
    const revisionMatch = buildInfo.revision?.match(/(\d+)-/);
    const revisionNum = revisionMatch ? revisionMatch[1] : buildInfo.revision;

    // Parse deploy time
    const deployTime = buildInfo.force_restart_timestamp 
        ? new Date(parseInt(buildInfo.force_restart_timestamp)).toLocaleString()
        : 'unknown';

    return (
        <div className="fixed bottom-4 left-4 z-50 bg-gray-900 text-white px-3 py-2 rounded-md shadow-lg border border-gray-700 text-xs font-mono">
            <div className="flex flex-col gap-1">
                <div>
                    <span className="text-gray-400">API:</span>{' '}
                    <span className="text-green-400 font-semibold">r{revisionNum}</span>
                </div>
                <div className="text-gray-500 text-[10px]">
                    {deployTime}
                </div>
            </div>
        </div>
    );
}
