export default function MetricCard({ label, value, helper, tone = "blue" }) {
  return (
    <article className={`react-metric react-metric--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {helper ? <p>{helper}</p> : null}
    </article>
  );
}
