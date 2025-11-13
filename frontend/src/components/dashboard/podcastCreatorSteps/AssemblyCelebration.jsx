import React, { useEffect, useRef, useState } from 'react';
import { PartyPopper, Sparkles } from 'lucide-react';
import { Button } from '../../ui/button';
import { Card, CardContent } from '../../ui/card';

// Party horn sound effect (using Web Audio API to generate a simple party horn sound)
const playPartyHorn = () => {
  try {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    // Create a party horn-like sound (multiple frequencies)
    oscillator.type = 'sawtooth';
    oscillator.frequency.setValueAtTime(440, audioContext.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(880, audioContext.currentTime + 0.1);
    oscillator.frequency.exponentialRampToValueAtTime(220, audioContext.currentTime + 0.2);
    
    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);
    
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.3);
    
    // Play a second shorter burst
    setTimeout(() => {
      const osc2 = audioContext.createOscillator();
      const gain2 = audioContext.createGain();
      osc2.connect(gain2);
      gain2.connect(audioContext.destination);
      osc2.type = 'sawtooth';
      osc2.frequency.setValueAtTime(660, audioContext.currentTime);
      osc2.frequency.exponentialRampToValueAtTime(1320, audioContext.currentTime + 0.08);
      gain2.gain.setValueAtTime(0.2, audioContext.currentTime);
      gain2.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.15);
      osc2.start(audioContext.currentTime);
      osc2.stop(audioContext.currentTime + 0.15);
    }, 150);
  } catch (err) {
    // Silently fail if audio context is not available
    console.debug('[Celebration] Audio not available:', err);
  }
};

// Confetti particle component
const ConfettiParticle = ({ delay, duration, left, color }) => {
  const [mounted, setMounted] = useState(false);
  
  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);
  
  if (!mounted) return null;
  
  return (
    <div
      className="absolute pointer-events-none"
      style={{
        left: `${left}%`,
        top: '-10px',
        animation: `confetti-fall ${duration}s linear forwards`,
        animationDelay: `${delay}ms`,
      }}
    >
      <div
        className="w-2 h-2 rounded-full"
        style={{
          backgroundColor: color,
          boxShadow: `0 0 6px ${color}`,
        }}
      />
    </div>
  );
};

export default function AssemblyCelebration({ assembledEpisode, onViewHistory, onBack }) {
  const [showConfetti, setShowConfetti] = useState(true);
  const confettiContainerRef = useRef(null);
  const hasPlayedSound = useRef(false);
  
  useEffect(() => {
    // Play party horn sound once when component mounts
    if (!hasPlayedSound.current) {
      playPartyHorn();
      hasPlayedSound.current = true;
    }
    
    // Stop confetti after 5 seconds
    const timer = setTimeout(() => {
      setShowConfetti(false);
    }, 5000);
    
    return () => clearTimeout(timer);
  }, []);
  
  // Generate confetti particles
  const confettiColors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2'];
  const particles = Array.from({ length: 50 }, (_, i) => ({
    id: i,
    delay: i * 50,
    duration: 2 + Math.random() * 2,
    left: Math.random() * 100,
    color: confettiColors[Math.floor(Math.random() * confettiColors.length)],
  }));
  
  return (
    <div className="relative min-h-[400px] flex items-center justify-center">
      {/* Confetti animation */}
      {showConfetti && (
        <div
          ref={confettiContainerRef}
          className="absolute inset-0 overflow-hidden pointer-events-none"
        >
          {particles.map((particle) => (
            <ConfettiParticle key={particle.id} {...particle} />
          ))}
        </div>
      )}
      
      {/* Celebration content */}
      <Card className="border-0 shadow-2xl bg-gradient-to-br from-purple-50 to-pink-50 relative z-10 max-w-2xl w-full">
        <CardContent className="p-8 space-y-6 text-center">
          {/* Animated icons */}
          <div className="flex justify-center items-center gap-4 mb-4">
            <PartyPopper className="w-16 h-16 text-yellow-500 animate-bounce" style={{ animationDelay: '0s' }} />
            <Sparkles className="w-20 h-20 text-purple-500 animate-pulse" />
            <PartyPopper className="w-16 h-16 text-pink-500 animate-bounce" style={{ animationDelay: '0.2s' }} />
          </div>
          
          {/* Success message */}
          <div className="space-y-3">
            <h2 className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-purple-600 to-pink-600">
              🎉 Congratulations! 🎉
            </h2>
            <p className="text-2xl font-semibold text-gray-800">
              Your episode is ready!
            </p>
            {assembledEpisode?.title && (
              <p className="text-lg text-gray-600 italic">
                "{assembledEpisode.title}"
              </p>
            )}
          </div>
          
          {/* Action buttons */}
          <div className="flex flex-col sm:flex-row gap-3 justify-center pt-4">
            <Button
              onClick={onViewHistory}
              size="lg"
              className="bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-semibold text-lg px-8 py-6 shadow-lg"
            >
              View in Episode History →
            </Button>
            <Button
              onClick={onBack}
              variant="outline"
              size="lg"
              className="px-8 py-6 text-lg"
            >
              Back to Dashboard
            </Button>
          </div>
          
          {/* Celebration message */}
          <p className="text-sm text-gray-500 pt-2">
            You did it! Your episode has been successfully assembled and is ready to share with the world.
          </p>
        </CardContent>
      </Card>
      
      {/* CSS for confetti animation */}
      <style>{`
        @keyframes confetti-fall {
          0% {
            transform: translateY(0) rotate(0deg);
            opacity: 1;
          }
          100% {
            transform: translateY(100vh) rotate(720deg);
            opacity: 0;
          }
        }
      `}</style>
    </div>
  );
}

