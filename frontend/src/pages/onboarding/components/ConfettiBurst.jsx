import React, { useEffect, useMemo } from "react";

const DEFAULT_COLORS = [
  "#FF6B6B",
  "#4ECDC4",
  "#45B7D1",
  "#FFA07A",
  "#98D8C8",
  "#F7DC6F",
  "#BB8FCE",
  "#85C1E2",
];

export function ConfettiBurst({ burstId, onComplete, colors = DEFAULT_COLORS }) {
  const palette = colors.length > 0 ? colors : DEFAULT_COLORS;
  const particles = useMemo(
    () =>
      Array.from({ length: 32 }, (_, index) => ({
        id: `${burstId}-${index}`,
        delay: Math.random() * 250,
        duration: 2 + Math.random() * 1.5,
        left: Math.random() * 100,
        color: palette[Math.floor(Math.random() * palette.length)],
      })),
    [burstId, palette]
  );

  useEffect(() => {
    const timer = setTimeout(() => onComplete?.(burstId), 2500);
    return () => clearTimeout(timer);
  }, [burstId, onComplete]);

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {particles.map((particle) => (
        <span
          key={particle.id}
          className="absolute block w-2 h-2 rounded-sm"
          style={{
            left: `${particle.left}%`,
            top: "-12px",
            backgroundColor: particle.color,
            animation: `onboarding-confetti-fall ${particle.duration}s linear forwards`,
            animationDelay: `${particle.delay}ms`,
          }}
        />
      ))}
      <style>{`
        @keyframes onboarding-confetti-fall {
          0% { transform: translate3d(0, 0, 0) rotate(0deg); opacity: 1; }
          100% { transform: translate3d(0, 110vh, 0) rotate(540deg); opacity: 0; }
        }
      `}</style>
    </div>
  );
}
