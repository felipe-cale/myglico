import { AlertIcon, ClockIcon, InboxIcon } from "./Icons";

const TONE_ICONS = { danger: AlertIcon, info: ClockIcon, neutral: InboxIcon };

export default function StateBlock({ title, description, tone = "neutral", icon, children }) {
  const ToneIcon = TONE_ICONS[tone] ?? InboxIcon;
  return (
    <div className={`react-state react-state--${tone}`}>
      <div className="react-state__icon" aria-hidden="true">
        {icon ?? <ToneIcon />}
      </div>
      <div>
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
        {children}
      </div>
    </div>
  );
}
