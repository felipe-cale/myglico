function Svg({ children, size = 20 }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" focusable="false" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

export function SendIcon({ size = 20 }) {
  return <Svg size={size}><path d="M12 19V5" /><path d="M5.5 11.5L12 5l6.5 6.5" /></Svg>;
}

export function MicIcon({ size = 20 }) {
  return <Svg size={size}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0" /><path d="M12 18v3" /></Svg>;
}

export function StopIcon({ size = 20 }) {
  return <Svg size={size}><rect x="6.5" y="6.5" width="11" height="11" rx="2.5" fill="currentColor" /></Svg>;
}

export function CameraIcon({ size = 20 }) {
  return <Svg size={size}><path d="M4 8.5A1.5 1.5 0 0 1 5.5 7H8l1.2-2h5.6L16 7h2.5A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z" /><circle cx="12" cy="13" r="3.4" /></Svg>;
}

export function ImageIcon({ size = 20 }) {
  return <Svg size={size}><rect x="4" y="5" width="16" height="14" rx="2.5" /><circle cx="9" cy="10" r="1.4" /><path d="M4.5 17l4.5-4.5 3.5 3.5 2.5-2.5 4.5 4.5" /></Svg>;
}

export function CloseIcon({ size = 18 }) {
  return <Svg size={size}><path d="M6 6l12 12M18 6L6 18" /></Svg>;
}

export function ToolsIcon({ size = 20 }) {
  return <Svg size={size}><path d="M4 7h9M17 7h3M4 17h3M11 17h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" /></Svg>;
}
