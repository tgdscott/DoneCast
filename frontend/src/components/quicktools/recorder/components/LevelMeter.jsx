import React from 'react';

/**
 * Audio level meter - SIMPLIFIED (no gain control slider)
 * @param {Object} props - Component props
 * @param {number} props.levelPct - Level percentage (0-1)
 * @param {string} props.levelColor - Color for the level bar
 */
export const LevelMeter = ({
  levelPct,
  levelColor
}) => {
  return (
    <div className="w-full max-w-md mx-auto">
      {/* Level Meter - Simple green bar, properly centered */}
      <div className="h-6 rounded-full bg-slate-900 relative overflow-hidden border border-slate-700">
        {/* Active level bar with smooth CSS transition */}
        <div 
          className="absolute left-0 top-0 h-full transition-all ease-out" 
          style={{ 
            width: `${Math.round(levelPct*100)}%`,
            background: levelPct > 0.08 
              ? 'linear-gradient(to right, #22c55e, #4ade80)' 
              : '#374151',
            transitionDuration: '100ms'
          }} 
        />
      </div>
    </div>
  );
};
