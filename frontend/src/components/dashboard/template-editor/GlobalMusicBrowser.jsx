import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Globe, Play, Pause, Plus, ChevronDown, ChevronRight, Music } from "lucide-react";
import { makeApi } from "@/lib/apiClient";

/**
 * GlobalMusicBrowser - Shows global music assets available to all users
 * Allows users to add global music to their templates
 */
const GlobalMusicBrowser = ({ token, onAddMusicToRule }) => {
  const [globalMusic, setGlobalMusic] = useState([]);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(true);  // Default to open so all 8 tracks are visible
  const [playingId, setPlayingId] = useState(null);
  const audioRef = useRef(null);  // For audio preview playback

  // Auto-fetch on mount to immediately show available tracks
  useEffect(() => {
    if (!globalMusic.length && !loading) {
      fetchGlobalMusic();
    }
  }, []);  // Run once on mount

  // Cleanup audio on unmount
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        try {
          audioRef.current.pause();
          audioRef.current = null;
        } catch {}
      }
    };
  }, []);

  const fetchGlobalMusic = async () => {
    setLoading(true);
    try {
      const api = makeApi(token);
      const data = await api.get('/api/music/assets?scope=global');
      // API returns { assets: [...] }, not a plain array
      const assets = data?.assets || [];
      setGlobalMusic(Array.isArray(assets) ? assets : []);
    } catch (err) {
      console.error('Failed to fetch global music:', err);
    } finally {
      setLoading(false);
    }
  };

  const handlePreview = (music) => {
    const previewUrl = music.preview_url || music.url || music.filename;
    
    if (!previewUrl) {
      console.warn('No preview URL available for music:', music);
      return;
    }

    // If already playing this track, stop it
    if (playingId === music.id) {
      try {
        if (audioRef.current) {
          audioRef.current.pause();
          audioRef.current = null;
        }
      } catch {}
      setPlayingId(null);
      return;
    }

    // Stop any currently playing audio
    try {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    } catch {}

    // Start playing the new track
    try {
      const audio = new Audio(previewUrl);
      audioRef.current = audio;
      setPlayingId(music.id);

      // Auto-stop after 20 seconds (preview mode)
      const stopAt = 20;
      const onTimeUpdate = () => {
        if (audio.currentTime >= stopAt) {
          audio.pause();
          setPlayingId(null);
          audio.removeEventListener('timeupdate', onTimeUpdate);
        }
      };
      audio.addEventListener('timeupdate', onTimeUpdate);

      // Handle natural end or errors
      audio.onended = () => {
        setPlayingId(null);
        audio.removeEventListener('timeupdate', onTimeUpdate);
      };
      audio.onerror = () => {
        console.error('Error playing preview for music:', music.display_name);
        setPlayingId(null);
        audio.removeEventListener('timeupdate', onTimeUpdate);
      };

      audio.play().catch((err) => {
        console.error('Failed to play preview:', err);
        setPlayingId(null);
      });
    } catch (err) {
      console.error('Error setting up audio preview:', err);
      setPlayingId(null);
    }
  };

  const handleAddToRule = (music) => {
    if (typeof onAddMusicToRule === 'function') {
      onAddMusicToRule(music);
    }
  };

  return (
    <Card className="mt-6">
      <CardHeader>
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center justify-between w-full group text-left"
        >
          <div className="flex items-center gap-2">
            <Globe className="w-5 h-5 text-blue-600" />
            <CardTitle className="text-base">Global Music Library</CardTitle>
            <Badge variant="secondary" className="ml-2">
              {globalMusic.length} tracks
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            {isOpen ? (
              <ChevronDown className="w-5 h-5 text-muted-foreground" />
            ) : (
              <ChevronRight className="w-5 h-5 text-muted-foreground" />
            )}
          </div>
        </button>
        <CardDescription>
          Browse music tracks provided by your platform admin. These are available to all users.
        </CardDescription>
      </CardHeader>
      {isOpen && (
        <CardContent>
            {loading ? (
              <div className="text-center py-8 text-muted-foreground">
                Loading global music library...
              </div>
            ) : globalMusic.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Music className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>No global music available yet.</p>
                <p className="text-xs mt-2">Contact your admin to add global music tracks.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {globalMusic.map((music) => (
                  <Card key={music.id} className="overflow-hidden border-2 hover:border-blue-300 transition-colors">
                    <CardContent className="p-4 space-y-3">
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <h4 className="font-semibold text-sm truncate" title={music.display_name}>
                            {music.display_name}
                          </h4>
                          {music.duration_s && (
                            <p className="text-xs text-muted-foreground">
                              {Math.floor(music.duration_s / 60)}:{String(Math.floor(music.duration_s % 60)).padStart(2, '0')}
                            </p>
                          )}
                        </div>
                        <Badge variant="outline" className="ml-2 shrink-0">
                          <Globe className="w-3 h-3 mr-1" />
                          Global
                        </Badge>
                      </div>
                      
                      {music.mood_tags_json && (() => {
                        try {
                          const moods = JSON.parse(music.mood_tags_json);
                          if (Array.isArray(moods) && moods.length > 0) {
                            return (
                              <div className="flex flex-wrap gap-1">
                                {moods.slice(0, 3).map((mood, idx) => (
                                  <Badge key={idx} variant="secondary" className="text-xs">
                                    {mood}
                                  </Badge>
                                ))}
                                {moods.length > 3 && (
                                  <Badge variant="secondary" className="text-xs">
                                    +{moods.length - 3}
                                  </Badge>
                                )}
                              </div>
                            );
                          }
                        } catch (e) {
                          // Invalid JSON, skip
                        }
                        return null;
                      })()}

                      <div className="flex gap-2 pt-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="flex-1"
                          onClick={() => handlePreview(music)}
                          disabled={!music.preview_url && !music.url && !music.filename}
                        >
                          {playingId === music.id ? (
                            <>
                              <Pause className="w-3 h-3 mr-1" />
                              Stop
                            </>
                          ) : (
                            <>
                              <Play className="w-3 h-3 mr-1" />
                              Preview
                            </>
                          )}
                        </Button>
                        <Button
                          variant="default"
                          size="sm"
                          className="flex-1"
                          onClick={() => handleAddToRule(music)}
                        >
                          <Plus className="w-3 h-3 mr-1" />
                          Add to Template
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </CardContent>
        )}
    </Card>
  );
};

export default GlobalMusicBrowser;
