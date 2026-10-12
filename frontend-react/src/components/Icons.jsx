function Svg({ children, size = 20 }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" focusable="false" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

export function ArrowRightIcon({ size = 18 }) {
  return <Svg size={size}><path d="M5 12h14M13 6l6 6-6 6" /></Svg>;
}

export function ArrowLeftIcon({ size = 16 }) {
  return <Svg size={size}><path d="M15 5l-7 7 7 7" /></Svg>;
}

export function ChevronDownIcon({ size = 18 }) {
  return <Svg size={size}><path d="M6 9l6 6 6-6" /></Svg>;
}

export function CopyIcon({ size = 18 }) {
  return <Svg size={size}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h9" /></Svg>;
}

export function CheckIcon({ size = 18 }) {
  return <Svg size={size}><path d="M5 12.5l4.5 4.5L19 7.5" /></Svg>;
}

export function HelpIcon({ size = 18 }) {
  return (
    <Svg size={size}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.6 9.3a2.5 2.5 0 0 1 4.8 1c0 1.7-2.4 2.1-2.4 3.7" />
      <path d="M12 17.2h.01" />
    </Svg>
  );
}
