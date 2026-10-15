export default function PasswordVisibilityIcon({ visible }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      {visible ? (
        <>
          <path d="M3 3l18 18" />
          <path d="M10.6 10.6a2 2 0 002.8 2.8" />
          <path d="M9.9 5.2A10.8 10.8 0 0112 5c5.2 0 8.8 4.6 9.7 6-.4.7-1.5 2.2-3.2 3.6M6.2 6.2C3.9 7.6 2.6 9.7 2.3 11c.9 1.4 4.5 6 9.7 6 1 0 1.9-.2 2.8-.5" />
        </>
      ) : (
        <>
          <path d="M2.3 12S5.8 6 12 6s9.7 6 9.7 6-3.5 6-9.7 6-9.7-6-9.7-6z" />
          <circle cx="12" cy="12" r="2.5" />
        </>
      )}
    </svg>
  );
}
