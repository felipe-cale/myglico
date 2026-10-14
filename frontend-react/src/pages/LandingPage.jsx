import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import useDocumentTitle from "../hooks/useDocumentTitle";
import { CameraIcon, MicIcon } from "../components/GlicoIcons";
import { CalendarIcon, ChartLineIcon, CheckIcon } from "../components/Icons";

const assetUrl = (path) => `${import.meta.env.BASE_URL}${path}`;

// One illustrative week: [day index, mg/dL]. The band 70-180 is the range reference, never a verdict.
const CHART_POINTS = [
  [0, 104], [0.5, 138], [1, 96], [1.5, 171], [2, 118], [2.5, 92], [3, 232], [3.5, 188],
  [4, 126], [4.5, 101], [5, 87], [5.5, 149], [6, 112],
];
const CHART = { width: 560, height: 190, left: 14, right: 14, top: 14, bottom: 14, min: 40, max: 260 };

function chartPath() {
  const x = (d) => CHART.left + (d / 6) * (CHART.width - CHART.left - CHART.right);
  const y = (v) => CHART.top + ((CHART.max - v) / (CHART.max - CHART.min)) * (CHART.height - CHART.top - CHART.bottom);
  return {
    x,
    y,
    line: CHART_POINTS.map(([d, v], i) => `${i === 0 ? "M" : "L"}${x(d).toFixed(1)} ${y(v).toFixed(1)}`).join(" "),
  };
}

const rangeClass = (value) => (value < 70 ? "is-low" : value > 180 ? "is-high" : "is-in-range");

function TextIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v7a2.5 2.5 0 0 1-2.5 2.5H11l-4 3.5V16h-.5A2.5 2.5 0 0 1 4 13.5z" transform="translate(.5 0)" />
      <path d="M8.5 8.5h7M8.5 11.5h4" />
    </svg>
  );
}

function PdfIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 3.5h7l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 19V5A1.5 1.5 0 0 1 7 3.5z" />
      <path d="M14 3.5V8h4M9 13h6M9 16.5h4" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3.5l7 2.6v5.4c0 4.3-2.9 7.6-7 9-4.1-1.4-7-4.7-7-9V6.1z" />
      <path d="M9 12l2.1 2.1L15.2 10" />
    </svg>
  );
}

function Mascot({ name, sizes, alt = "", className, eager = false, width, height }) {
  const webp = (size) => assetUrl(`img/${name}-${size}.webp`);
  const [small, large] = sizes;
  return (
    <img
      className={className}
      src={webp(large)}
      srcSet={`${webp(small)} ${small}w, ${webp(large)} ${large}w`}
      sizes={`(max-width: 700px) ${Math.min(small, 320)}px, ${Math.min(large, 520)}px`}
      alt={alt}
      width={width}
      height={height}
      loading={eager ? "eager" : "lazy"}
      fetchpriority={eager ? "high" : undefined}
      decoding="async"
    />
  );
}

function Actions({ onDark = false }) {
  const { t } = useTranslation();
  return (
    <div className={`lp-actions${onDark ? " lp-actions--on-dark" : ""}`}>
      <Link to="/register" className="lp-button lp-button--primary">
        {t("auth.register")}
      </Link>
      <Link to="/login" className="lp-button lp-button--secondary">
        {t("auth.login")}
      </Link>
    </div>
  );
}

function ChatMock() {
  const { t } = useTranslation();
  const modes = t("landing.glico.modes", { returnObjects: true });
  const icons = [<TextIcon key="text" />, <CameraIcon key="photo" size={18} />, <MicIcon key="voice" size={18} />];
  return (
    <div className="lp-chat" aria-hidden="true">
      <div className="lp-chat__modes">
        {modes.map((label, index) => (
          <span key={label} className={`lp-chat__mode${index === 0 ? " is-on" : ""}`}>
            {icons[index]}
            {label}
          </span>
        ))}
      </div>
      <p className="lp-chat__user">{t("landing.glico.user")}</p>
      <div className="lp-chat__row">
        <Mascot name="mascote-avatar" sizes={[96, 192]} className="lp-chat__avatar" width="56" height="56" />
        <div className="lp-chat__bot">
          <p>{t("landing.glico.bot")}</p>
          <div className="lp-chat__buttons">
            <span className="lp-chat__save">
              <CheckIcon size={16} />
              {t("landing.glico.save")}
            </span>
            <span className="lp-chat__fix">{t("landing.glico.fix")}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChartMock() {
  const { t } = useTranslation();
  const { x, y, line } = chartPath();
  return (
    <div className="lp-chart" role="img" aria-label={t("landing.indicators.chartAlt")}>
      <svg viewBox={`0 0 ${CHART.width} ${CHART.height}`} aria-hidden="true" focusable="false">
        <rect className="lp-chart__band" x="0" y={y(180)} width={CHART.width} height={y(70) - y(180)} rx="14" />
        <path className="lp-chart__line" d={line} />
        {CHART_POINTS.map(([d, v]) => (
          <circle key={d} className={`lp-chart__dot ${rangeClass(v)}`} cx={x(d)} cy={y(v)} r="6" />
        ))}
      </svg>
      <ul className="lp-legend">
        <li className="is-in-range">{t("landing.indicators.inRange")}</li>
        <li className="is-high">{t("landing.indicators.high")}</li>
        <li className="is-low">{t("landing.indicators.low")}</li>
      </ul>
    </div>
  );
}

function WeekMock() {
  const { t } = useTranslation();
  const days = t("landing.atypical.days", { returnObjects: true });
  return (
    <div className="lp-week" aria-hidden="true">
      <ol className="lp-week__days">
        {days.map((day, index) => (
          <li key={index} className={index === 3 ? "is-atypical" : undefined}>
            {day}
          </li>
        ))}
      </ol>
      <div className="lp-week__note">
        <span className="lp-week__chip">{t("landing.atypical.chip")}</span>
        <span className="lp-week__ask">{t("landing.atypical.ask")}</span>
      </div>
    </div>
  );
}

function SheetMock() {
  const { t } = useTranslation();
  return (
    <div className="lp-sheet" aria-hidden="true">
      <div className="lp-sheet__page">
        <span className="lp-sheet__title">{t("landing.report.sheet")}</span>
        <span className="lp-sheet__rule" />
        <span className="lp-sheet__bars">
          {[46, 70, 38, 84, 58, 66, 42].map((height, index) => (
            <i key={index} style={{ height: `${height}%` }} />
          ))}
        </span>
        <span className="lp-sheet__rule lp-sheet__rule--short" />
        <span className="lp-sheet__rule" />
      </div>
      <ul className="lp-sheet__langs">
        {t("landing.report.languages", { returnObjects: true }).map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ul>
    </div>
  );
}

export default function LandingPage() {
  const { t } = useTranslation();
  useDocumentTitle(null);

  return (
    <div className="react-page lp">
      <section className="lp-hero">
        <div className="lp-hero__copy">
          <h1>{t("landing.hero.title")}</h1>
          <p className="lp-hero__body">{t("landing.hero.body")}</p>
          <Actions onDark />
          <p className="lp-hero__note">
            <ShieldIcon />
            {t("landing.hero.badgeControl")}
          </p>
        </div>
        <div className="lp-hero__art">
          <Mascot
            name="mascote-medidor"
            sizes={[480, 900]}
            alt={t("landing.hero.mascotAlt")}
            className="lp-hero__mascot"
            width="520"
            height="520"
            eager
          />
        </div>
      </section>

      <section className="lp-feature lp-feature--glico">
        <div className="lp-feature__copy">
          <h2>{t("landing.glico.title")}</h2>
          <p>{t("landing.glico.body")}</p>
          <small className="lp-example">{t("landing.example")}</small>
        </div>
        <ChatMock />
      </section>

      <div className="lp-duo">
        <section className="lp-feature lp-feature--indicators">
          <div className="lp-feature__icon">
            <ChartLineIcon size={24} />
          </div>
          <h2>{t("landing.indicators.title")}</h2>
          <p>{t("landing.indicators.body")}</p>
          <ChartMock />
        </section>
        <section className="lp-feature lp-feature--atypical">
          <div className="lp-feature__icon">
            <CalendarIcon size={24} />
          </div>
          <h2>{t("landing.atypical.title")}</h2>
          <p>{t("landing.atypical.body")}</p>
          <WeekMock />
        </section>
      </div>

      <section className="lp-feature lp-feature--report">
        <SheetMock />
        <div className="lp-feature__copy">
          <div className="lp-feature__icon">
            <PdfIcon />
          </div>
          <h2>{t("landing.report.title")}</h2>
          <p>{t("landing.report.body")}</p>
        </div>
      </section>

      <section className="lp-consent">
        <div className="lp-consent__lead">
          <div className="lp-feature__icon">
            <ShieldIcon />
          </div>
          <h2>{t("landing.consent.title")}</h2>
          <p>{t("landing.consent.body")}</p>
        </div>
        <div className="lp-consent__roles">
          {["patient", "doctor"].map((audience) => (
            <div key={audience}>
              <h3>{t(`landing.${audience}.title`)}</h3>
              <p>{t(`landing.${audience}.body`)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="lp-cta">
        <Mascot name="mascote-avatar" sizes={[192, 420]} className="lp-cta__avatar" width="132" height="132" />
        <div>
          <h2>{t("landing.cta.title")}</h2>
          <p>{t("landing.cta.body")}</p>
          <Actions />
        </div>
      </section>
    </div>
  );
}
