export default function StateBlock({ title, description, tone = "neutral", children }) {
  return (
    <div className={`react-state react-state--${tone}`}>
      <div className="react-state__icon" aria-hidden="true" />
      <div>
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
        {children}
      </div>
    </div>
  );
}
