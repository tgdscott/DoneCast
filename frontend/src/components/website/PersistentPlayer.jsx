/**
 * Persistent Audio Player Component
 * 
 * Spreaker-style player with:
 * - Banner player at bottom of page
 * - Full-screen player modal
 * - Queue management
 * - Play/pause, skip controls
 */

import { useState, useEffect, useRef } from "react";
import { Play, Pause, SkipBack, SkipForward, ChevronUp, ChevronDown, X, List, Shuffle, Repeat } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export default function PersistentPlayer() {
  const [currentEpisode, setCurrentEpisode] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [queue, setQueue] = useState([]);
  const [queueIndex, setQueueIndex] = useState(0);
  const [showFullPlayer, setShowFullPlayer] = useState(false);
  const [shuffle, setShuffle] = useState(false);
  const [repeat, setRepeat] = useState(false); // false, 'one', 'all'
  
  const audioRef = useRef(null);
  const progressIntervalRef = useRef(null);

  // Format time helper
  const formatTime = (seconds) => {
    if (!seconds || isNaN(seconds)) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Format duration helper
  const formatDuration = (seconds) => {
    if (!seconds) return '';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs > 0 ? secs + 's' : ''}`;
    }
    return `${minutes}m ${secs > 0 ? secs + 's' : ''}`;
  };

  // Listen for play-episode events
  useEffect(() => {
    const handlePlayEpisode = (event) => {
      const episode = event.detail.episode;
      
      // Add to queue if not already there and find index
      setQueue(prev => {
        const exists = prev.some(ep => ep.id === episode.id);
        let newQueue = prev;
        
        if (!exists) {
          newQueue = [...prev, episode];
        }
        
        // Find index in the new queue
        const index = newQueue.findIndex(ep => ep.id === episode.id);
        if (index !== -1) {
          setQueueIndex(index);
        }
        
        return newQueue;
      });
      
      setCurrentEpisode(episode);
      setCurrentTime(0);
      setIsPlaying(true);
      
      // If audio element exists, load and play
      if (audioRef.current) {
        audioRef.current.src = episode.audio_url;
        audioRef.current.load();
        audioRef.current.play().catch(err => {
          console.error("Failed to play audio:", err);
          setIsPlaying(false);
        });
      }
    };

    const handleAddToQueue = (event) => {
      const episode = event.detail.episode;
      setQueue(prev => {
        // Don't add duplicates
        const exists = prev.some(ep => ep.id === episode.id);
        if (!exists) {
          return [...prev, episode];
        }
        return prev;
      });
    };

    window.addEventListener('play-episode', handlePlayEpisode);
    window.addEventListener('add-to-queue', handleAddToQueue);

    return () => {
      window.removeEventListener('play-episode', handlePlayEpisode);
      window.removeEventListener('add-to-queue', handleAddToQueue);
    };
  }, []);

  // Audio element event handlers
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handleTimeUpdate = () => {
      setCurrentTime(audio.currentTime);
    };

    const handleDurationChange = () => {
      setDuration(audio.duration);
    };

    const handleEnded = () => {
      setIsPlaying(false);
      setCurrentTime(0);
      
      // Auto-play next in queue
      if (queue.length > 0 && queueIndex < queue.length - 1) {
        const nextIndex = queueIndex + 1;
        setQueueIndex(nextIndex);
        const nextEpisode = queue[nextIndex];
        setCurrentEpisode(nextEpisode);
        audio.src = nextEpisode.audio_url;
        audio.load();
        audio.play();
        setIsPlaying(true);
      } else if (repeat === 'all' && queue.length > 0) {
        // Repeat all - go back to first
        setQueueIndex(0);
        const firstEpisode = queue[0];
        setCurrentEpisode(firstEpisode);
        audio.src = firstEpisode.audio_url;
        audio.load();
        audio.play();
        setIsPlaying(true);
      } else if (repeat === 'one' && currentEpisode) {
        // Repeat one - replay current
        audio.currentTime = 0;
        audio.play();
        setIsPlaying(true);
      }
    };

    const handlePlay = () => setIsPlaying(true);
    const handlePause = () => setIsPlaying(false);
    const handleError = () => {
      setIsPlaying(false);
      console.error("Audio playback error");
    };

    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('durationchange', handleDurationChange);
    audio.addEventListener('ended', handleEnded);
    audio.addEventListener('play', handlePlay);
    audio.addEventListener('pause', handlePause);
    audio.addEventListener('error', handleError);

    return () => {
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('durationchange', handleDurationChange);
      audio.removeEventListener('ended', handleEnded);
      audio.removeEventListener('play', handlePlay);
      audio.removeEventListener('pause', handlePause);
      audio.removeEventListener('error', handleError);
    };
  }, [queue, queueIndex, repeat, currentEpisode]);

  // Update progress bar
  useEffect(() => {
    if (isPlaying) {
      progressIntervalRef.current = setInterval(() => {
        if (audioRef.current) {
          setCurrentTime(audioRef.current.currentTime);
        }
      }, 100);
    } else {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
      }
    }

    return () => {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
      }
    };
  }, [isPlaying]);

  // Play/pause handler
  const handlePlayPause = () => {
    if (!audioRef.current || !currentEpisode) return;

    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play().catch(err => {
        console.error("Failed to play:", err);
      });
    }
  };

  // Skip handlers
  const handleSkipBack = () => {
    if (!audioRef.current) return;
    audioRef.current.currentTime = Math.max(0, audioRef.current.currentTime - 10);
  };

  const handleSkipForward = () => {
    if (!audioRef.current) return;
    audioRef.current.currentTime = Math.min(
      audioRef.current.duration,
      audioRef.current.currentTime + 30
    );
  };

  // Seek handler
  const handleSeek = (e) => {
    if (!audioRef.current) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const percent = (e.clientX - rect.left) / rect.width;
    const newTime = percent * duration;
    audioRef.current.currentTime = newTime;
    setCurrentTime(newTime);
  };

  // Volume handler
  const handleVolumeChange = (e) => {
    const newVolume = parseFloat(e.target.value);
    setVolume(newVolume);
    if (audioRef.current) {
      audioRef.current.volume = newVolume;
    }
  };

  // Next/Previous episode
  const handlePrevious = () => {
    if (queue.length === 0 || queueIndex === 0) return;
    const prevIndex = queueIndex - 1;
    setQueueIndex(prevIndex);
    const prevEpisode = queue[prevIndex];
    setCurrentEpisode(prevEpisode);
    if (audioRef.current) {
      audioRef.current.src = prevEpisode.audio_url;
      audioRef.current.load();
      audioRef.current.play();
      setIsPlaying(true);
    }
  };

  const handleNext = () => {
    if (queue.length === 0 || queueIndex >= queue.length - 1) {
      if (repeat === 'all') {
        // Loop back to start
        setQueueIndex(0);
        const firstEpisode = queue[0];
        setCurrentEpisode(firstEpisode);
        if (audioRef.current) {
          audioRef.current.src = firstEpisode.audio_url;
          audioRef.current.load();
          audioRef.current.play();
          setIsPlaying(true);
        }
      }
      return;
    }
    const nextIndex = queueIndex + 1;
    setQueueIndex(nextIndex);
    const nextEpisode = queue[nextIndex];
    setCurrentEpisode(nextEpisode);
    if (audioRef.current) {
      audioRef.current.src = nextEpisode.audio_url;
      audioRef.current.load();
      audioRef.current.play();
      setIsPlaying(true);
    }
  };

  // Remove from queue
  const handleRemoveFromQueue = (index) => {
    setQueue(prev => prev.filter((_, i) => i !== index));
    if (index < queueIndex) {
      setQueueIndex(prev => prev - 1);
    } else if (index === queueIndex && queue.length > 1) {
      // If removing current, play next
      if (index < queue.length - 1) {
        handleNext();
      } else {
        handlePrevious();
      }
    }
  };

  // Always render the player (even if empty) - Spreaker style
  // The player will be minimized/hidden when no episode is playing

  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0;

  // Always render player - even when no episode is playing (Spreaker style)
  // If no episode, show minimal player
  useEffect(() => {
    console.log('[PersistentPlayer] Component mounted/updated, currentEpisode:', currentEpisode?.title || 'NONE');
  }, [currentEpisode]);
  
  // CRITICAL: Always render - this should be visible at bottom of page
  if (!currentEpisode) {
    console.log('[PersistentPlayer] Rendering empty player (no episode)');
    return (
      <div 
        className="fixed bottom-0 left-0 right-0 bg-slate-900 text-white z-[9999] border-t-2 border-red-500 shadow-2xl h-20 flex items-center justify-center"
        style={{ 
          position: 'fixed', 
          bottom: 0, 
          left: 0, 
          right: 0, 
          zIndex: 9999,
          backgroundColor: '#0f172a',
          minHeight: '80px'
        }}
      >
        <p className="text-sm text-slate-400 font-semibold">No episode playing</p>
      </div>
    );
  }

  return (
    <>
      {/* Hidden audio element */}
      <audio ref={audioRef} preload="metadata" />

      {/* Banner Player (bottom of page) */}
      <div 
        className="fixed bottom-0 left-0 right-0 bg-slate-900 text-white z-[9999] border-t border-slate-700 shadow-2xl"
        style={{ position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 9999 }}
      >
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center gap-4">
            {/* Episode Info */}
            <div className="flex items-center gap-3 flex-1 min-w-0">
              {currentEpisode.cover_url && (
                <img
                  src={currentEpisode.cover_url}
                  alt={currentEpisode.title}
                  className="w-12 h-12 rounded object-cover flex-shrink-0"
                  onError={(e) => {
                    e.target.style.display = 'none';
                  }}
                />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{currentEpisode.title}</p>
                <p className="text-xs text-slate-400 truncate">
                  {currentEpisode.podcast_title || 'Podcast'}
                </p>
              </div>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSkipBack}
                className="text-white hover:bg-slate-800 h-8 w-8 p-0"
                title="Skip back 10s"
              >
                <SkipBack className="h-4 w-4" />
              </Button>
              
              <Button
                variant="ghost"
                size="sm"
                onClick={handlePlayPause}
                className="text-white hover:bg-slate-800 h-10 w-10 p-0"
              >
                {isPlaying ? (
                  <Pause className="h-5 w-5" />
                ) : (
                  <Play className="h-5 w-5" />
                )}
              </Button>
              
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSkipForward}
                className="text-white hover:bg-slate-800 h-8 w-8 p-0"
                title="Skip forward 30s"
              >
                <SkipForward className="h-4 w-4" />
              </Button>
            </div>

            {/* Progress & Time */}
            <div className="hidden md:flex items-center gap-3 flex-1 max-w-md">
              <span className="text-xs text-slate-400 min-w-[40px]">
                {formatTime(currentTime)}
              </span>
              <div
                className="flex-1 h-1 bg-slate-700 rounded-full cursor-pointer relative group"
                onClick={handleSeek}
              >
                <div
                  className="h-full bg-white rounded-full transition-all"
                  style={{ width: `${progressPercent}%` }}
                />
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                  <div className="h-3 w-3 bg-white rounded-full shadow-lg" />
                </div>
              </div>
              <span className="text-xs text-slate-400 min-w-[40px]">
                {formatTime(duration)}
              </span>
            </div>

            {/* Expand Button */}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowFullPlayer(true)}
              className="text-white hover:bg-slate-800 h-8 w-8 p-0"
              title="Open full player"
            >
              <ChevronUp className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Full Screen Player Modal */}
      <Dialog open={showFullPlayer} onOpenChange={setShowFullPlayer}>
        <DialogContent className="max-w-2xl bg-slate-900 text-white border-slate-700">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center justify-between">
              <span>Now Playing</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowFullPlayer(false)}
                className="text-white hover:bg-slate-800 h-8 w-8 p-0"
              >
                <ChevronDown className="h-4 w-4" />
              </Button>
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-6 py-6">
            {/* Episode Art & Info */}
            <div className="text-center">
              {currentEpisode.cover_url && (
                <img
                  src={currentEpisode.cover_url}
                  alt={currentEpisode.title}
                  className="w-64 h-64 mx-auto rounded-lg object-cover mb-6 shadow-xl"
                  onError={(e) => {
                    e.target.style.display = 'none';
                  }}
                />
              )}
              <h2 className="text-2xl font-bold mb-2">{currentEpisode.title}</h2>
              <p className="text-slate-400 mb-4">
                {currentEpisode.podcast_title || 'Podcast'}
              </p>
              {currentEpisode.description && (
                <p className="text-sm text-slate-300 max-w-md mx-auto line-clamp-3">
                  {currentEpisode.description}
                </p>
              )}
            </div>

            {/* Progress Bar */}
            <div className="space-y-2">
              <div
                className="w-full h-2 bg-slate-700 rounded-full cursor-pointer relative group"
                onClick={handleSeek}
              >
                <div
                  className="h-full bg-white rounded-full transition-all"
                  style={{ width: `${progressPercent}%` }}
                />
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                  <div className="h-4 w-4 bg-white rounded-full shadow-lg" />
                </div>
              </div>
              <div className="flex justify-between text-sm text-slate-400">
                <span>{formatTime(currentTime)}</span>
                <span>{formatTime(duration)}</span>
              </div>
            </div>

            {/* Main Controls */}
            <div className="flex items-center justify-center gap-4">
              <Button
                variant="ghost"
                size="lg"
                onClick={() => setShuffle(!shuffle)}
                className={`text-white hover:bg-slate-800 ${shuffle ? 'bg-slate-800' : ''}`}
                title="Shuffle"
              >
                <Shuffle className="h-5 w-5" />
              </Button>

              <Button
                variant="ghost"
                size="lg"
                onClick={handlePrevious}
                disabled={queue.length === 0 || queueIndex === 0}
                className="text-white hover:bg-slate-800 disabled:opacity-50"
                title="Previous"
              >
                <SkipBack className="h-6 w-6" />
              </Button>

              <Button
                variant="default"
                size="lg"
                onClick={handlePlayPause}
                className="bg-white text-slate-900 hover:bg-slate-100 h-16 w-16 rounded-full"
              >
                {isPlaying ? (
                  <Pause className="h-8 w-8" />
                ) : (
                  <Play className="h-8 w-8 ml-1" />
                )}
              </Button>

              <Button
                variant="ghost"
                size="lg"
                onClick={handleNext}
                disabled={queue.length === 0 || (queueIndex >= queue.length - 1 && repeat !== 'all')}
                className="text-white hover:bg-slate-800 disabled:opacity-50"
                title="Next"
              >
                <SkipForward className="h-6 w-6" />
              </Button>

              <Button
                variant="ghost"
                size="lg"
                onClick={() => {
                  if (repeat === false) setRepeat('all');
                  else if (repeat === 'all') setRepeat('one');
                  else setRepeat(false);
                }}
                className={`text-white hover:bg-slate-800 ${repeat ? 'bg-slate-800' : ''}`}
                title={repeat === 'one' ? 'Repeat One' : repeat === 'all' ? 'Repeat All' : 'Repeat Off'}
              >
                <Repeat className={`h-5 w-5 ${repeat === 'one' ? 'text-white' : ''}`} />
              </Button>
            </div>

            {/* Skip Controls */}
            <div className="flex items-center justify-center gap-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSkipBack}
                className="text-slate-400 hover:text-white hover:bg-slate-800"
              >
                <SkipBack className="h-4 w-4 mr-1" />
                10s
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSkipForward}
                className="text-slate-400 hover:text-white hover:bg-slate-800"
              >
                30s
                <SkipForward className="h-4 w-4 ml-1" />
              </Button>
            </div>

            {/* Volume Control */}
            <div className="flex items-center gap-3">
              <span className="text-sm text-slate-400 min-w-[60px]">Volume</span>
              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={volume}
                onChange={handleVolumeChange}
                className="flex-1 h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-white"
              />
              <span className="text-sm text-slate-400 min-w-[40px] text-right">
                {Math.round(volume * 100)}%
              </span>
            </div>

            {/* Queue */}
            {queue.length > 0 && (
              <div className="border-t border-slate-700 pt-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold">Queue ({queue.length})</h3>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setQueue([])}
                    className="text-slate-400 hover:text-white text-xs"
                  >
                    Clear
                  </Button>
                </div>
                <div className="max-h-48 overflow-y-auto space-y-2">
                  {queue.map((ep, index) => (
                    <div
                      key={ep.id}
                      className={`flex items-center gap-3 p-2 rounded hover:bg-slate-800 ${
                        index === queueIndex ? 'bg-slate-800 border border-slate-600' : ''
                      }`}
                    >
                      {ep.cover_url && (
                        <img
                          src={ep.cover_url}
                          alt={ep.title}
                          className="w-10 h-10 rounded object-cover"
                          onError={(e) => {
                            e.target.style.display = 'none';
                          }}
                        />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm truncate ${index === queueIndex ? 'font-semibold' : ''}`}>
                          {ep.title}
                        </p>
                        {(ep.duration_seconds || ep.duration) && (
                          <p className="text-xs text-slate-400">
                            {formatDuration(ep.duration_seconds || ep.duration)}
                          </p>
                        )}
                      </div>
                      {index === queueIndex && (
                        <span className="text-xs text-slate-400">Now Playing</span>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveFromQueue(index)}
                        className="text-slate-400 hover:text-white h-6 w-6 p-0"
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

