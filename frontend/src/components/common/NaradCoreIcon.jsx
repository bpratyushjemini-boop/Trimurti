import React from 'react';

/**
 * NaradCoreIcon: Indian-inspired HUD icon for NARAD.
 * Features concentric rotating rings with saffron-cyan gradient,
 * a central Trishula-inspired motif, and atmospheric glow.
 */
export default function NaradCoreIcon({ size = 28, animated = true, className = '' }) {
  return (
    <div 
      className={`relative flex items-center justify-center select-none flex-shrink-0 ${className}`}
      style={{ width: size, height: size }}
      title="NARAD — Neural Assistant for Rizz & Absolute Destruction"
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full"
      >
        <defs>
          {/* Radial cyan-saffron ambient glow */}
          <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#00f0ff" stopOpacity="0.4" />
            <stop offset="45%" stopColor="#FF6B00" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#00f0ff" stopOpacity="0" />
          </radialGradient>
          
          <linearGradient id="saffronCyanGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FF6B00" />
            <stop offset="50%" stopColor="#FFD700" />
            <stop offset="100%" stopColor="#00f0ff" />
          </linearGradient>

          <linearGradient id="cyanGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#00f0ff" />
            <stop offset="100%" stopColor="#0284c7" />
          </linearGradient>

          <linearGradient id="saffronGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FF6B00" />
            <stop offset="100%" stopColor="#FFD700" />
          </linearGradient>
        </defs>

        {/* Ambient background glow */}
        <circle cx="50" cy="50" r="47" fill="url(#coreGlow)" />

        {/* Outer segmented ring — saffron-cyan gradient (slow clockwise) */}
        <g className={animated ? 'animate-spin-slow origin-center' : ''}>
          <circle
            cx="50"
            cy="50"
            r="44"
            stroke="url(#saffronCyanGrad)"
            strokeWidth="1.8"
            strokeDasharray="8 6 18 6"
            strokeOpacity="0.8"
          />
          {/* Cardinal tick points — alternating saffron/cyan */}
          <circle cx="50" cy="5" r="2" fill="#FF6B00" />
          <circle cx="50" cy="95" r="2" fill="#00f0ff" />
          <circle cx="5" cy="50" r="2" fill="#00f0ff" />
          <circle cx="95" cy="50" r="2" fill="#FF6B00" />
        </g>

        {/* Middle reverse rotating ring with saffron accents */}
        <g className={animated ? 'animate-spin-reverse-slow origin-center' : ''}>
          <circle
            cx="50"
            cy="50"
            r="35"
            stroke="#38bdf8"
            strokeWidth="1.2"
            strokeDasharray="20 10 30 12"
            strokeOpacity="0.5"
          />
          {/* Diagonal ticks — saffron */}
          <line x1="24" y1="24" x2="28" y2="28" stroke="#FF6B00" strokeWidth="1.8" strokeOpacity="0.7" />
          <line x1="76" y1="24" x2="72" y2="28" stroke="#FF6B00" strokeWidth="1.8" strokeOpacity="0.7" />
          <line x1="24" y1="76" x2="28" y2="72" stroke="#00f0ff" strokeWidth="1.8" strokeOpacity="0.7" />
          <line x1="76" y1="76" x2="72" y2="72" stroke="#00f0ff" strokeWidth="1.8" strokeOpacity="0.7" />
        </g>

        {/* Inner static containment ring */}
        <circle
          cx="50"
          cy="50"
          r="24"
          stroke="url(#saffronCyanGrad)"
          strokeWidth="0.8"
          strokeOpacity="0.35"
        />

        {/* Central Trishula-inspired motif */}
        <g className={animated ? 'animate-cyan-pulse origin-center' : ''}>
          {/* Diamond shape (tilak-inspired) */}
          <polygon
            points="50,30 62,50 50,70 38,50"
            stroke="url(#saffronCyanGrad)"
            strokeWidth="1.6"
            fill="rgba(0, 240, 255, 0.1)"
          />
          {/* Central vertical prong (trishula center) */}
          <line x1="50" y1="32" x2="50" y2="44" stroke="#FFD700" strokeWidth="1.5" strokeOpacity="0.8" />
          {/* Side prongs */}
          <line x1="40" y1="42" x2="45" y2="46" stroke="#FF6B00" strokeWidth="1.2" strokeOpacity="0.6" />
          <line x1="60" y1="42" x2="55" y2="46" stroke="#FF6B00" strokeWidth="1.2" strokeOpacity="0.6" />
          
          {/* Radiant Core */}
          <circle cx="50" cy="50" r="6.5" fill="#00f0ff" className="drop-shadow-[0_0_8px_#00f0ff]" />
          <circle cx="50" cy="50" r="3.5" fill="#FFD700" className="drop-shadow-[0_0_4px_#FFD700]" />
          <circle cx="50" cy="50" r="1.5" fill="#ffffff" />
        </g>
      </svg>
    </div>
  );
}
