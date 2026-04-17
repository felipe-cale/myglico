export default function StateBlock({ title, description, tone = "neutral" }) {
  return (
    <div className={`react-state react-state--${tone}`}>
      <div className="react-state__icon" aria-hidden="true" />
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
    </div>
  );
}
