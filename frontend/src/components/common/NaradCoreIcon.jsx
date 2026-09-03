import React from 'react';

/**
 * NaradCoreIcon: Bespoke JARVIS/HUD-inspired ARC Reactor icon for NARAD.
 * Features concentric rotating geometric rings, technical tick marks,
 * and a pulsing central intelligence core.
 */
export default function NaradCoreIcon({ size = 28, animated = true, className = '' }) {
  return (
    <div 
      className={`relative flex items-center justify-center select-none flex-shrink-0 ${className}`}
      style={{ width: size, height: size }}
      title="NARAD Intelligent Core"
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
          {/* Subtle radial cyan glow */}
          <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#00f0ff" stopOpacity="0.45" />
            <stop offset="70%" stopColor="#0284c7" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#00f0ff" stopOpacity="0" />
          </radialGradient>
          
          <linearGradient id="cyanGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#00f0ff" />
            <stop offset="100%" stopColor="#0284c7" />
          </linearGradient>
        </defs>

        {/* Ambient background glow circle */}
        <circle cx="50" cy="50" r="46" fill="url(#coreGlow)" />

        {/* Outer segmented ring (slow clockwise) */}
        <g className={animated ? 'animate-spin-slow origin-center' : ''}>
          <circle
            cx="50"
            cy="50"
            r="44"
            stroke="#00f0ff"
            strokeWidth="1.5"
            strokeDasharray="6 8 16 8"
            strokeOpacity="0.75"
          />
          {/* North/South/East/West technical tick points */}
          <circle cx="50" cy="5" r="1.5" fill="#00f0ff" />
          <circle cx="50" cy="95" r="1.5" fill="#00f0ff" />
          <circle cx="5" cy="50" r="1.5" fill="#00f0ff" />
          <circle cx="95" cy="50" r="1.5" fill="#00f0ff" />
        </g>

        {/* Middle reverse rotating ring with gap sectors */}
        <g className={animated ? 'animate-spin-reverse-slow origin-center' : ''}>
          <circle
            cx="50"
            cy="50"
            r="35"
            stroke="#38bdf8"
            strokeWidth="1.2"
            strokeDasharray="18 12 30 14"
            strokeOpacity="0.6"
          />
          {/* Angular cross ticks */}
          <line x1="25" y1="25" x2="29" y2="29" stroke="#00f0ff" strokeWidth="1.5" strokeOpacity="0.8" />
          <line x1="75" y1="25" x2="71" y2="29" stroke="#00f0ff" strokeWidth="1.5" strokeOpacity="0.8" />
          <line x1="25" y1="75" x2="29" y2="71" stroke="#00f0ff" strokeWidth="1.5" strokeOpacity="0.8" />
          <line x1="75" y1="75" x2="71" y2="71" stroke="#00f0ff" strokeWidth="1.5" strokeOpacity="0.8" />
        </g>

        {/* Inner static containment ring */}
        <circle
          cx="50"
          cy="50"
          r="23"
          stroke="#00f0ff"
          strokeWidth="1"
          strokeOpacity="0.4"
        />

        {/* Central Pulsing Iris */}
        <g className={animated ? 'animate-cyan-pulse origin-center' : ''}>
          {/* Inner hexagon */}
          <polygon
            points="50,33 65,42 65,58 50,67 35,58 35,42"
            stroke="#00f0ff"
            strokeWidth="1.8"
            fill="rgba(0, 240, 255, 0.15)"
          />
          {/* Radiant Core Dot */}
          <circle cx="50" cy="50" r="6" fill="#00f0ff" className="drop-shadow-[0_0_6px_#00f0ff]" />
          <circle cx="50" cy="50" r="2.5" fill="#ffffff" />
        </g>
      </svg>
    </div>
  );
}
