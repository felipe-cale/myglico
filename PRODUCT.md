# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary: the patient.** A person with diabetes following their own
  glycemia day to day, mostly on a phone. They record manual glucose
  readings, review their own period and indicators, manage which doctors
  may follow them, and answer their doctor's questions about atypical days.
- **Secondary: the doctor.** A clinician reviewing the patients who granted
  them an active link, usually on desktop. They scan the linked-patient list,
  open a patient's detail, and open questions (investigations) about
  atypical days.

## Product Purpose

MyGlico is both an academic MVP and a product meant to work for real
patients and doctors. As research, it demonstrates (SIAc 2026 article,
public UCI Diabetes dataset) relational ingestion, glycemic analytics,
patient-controlled doctor links, CSCW collaboration around atypical days,
and end-to-end provenance (PROV-JSON / PROV-TTL / PROV-O). As a product,
success means a patient can keep track of their glycemia and talk to their
doctor about specific days without friction, and a doctor can see only what
the patient allowed.

## Positioning

Every reading and every collaboration event is traceable: the chain
`RawRecord -> GlucoseMeasurement -> Patient` and the CSCW events are recorded
as provenance, and the patient controls which doctor sees their data through
explicit, revocable links.

## Operating Context

- Patient flows: registration (with privacy notice acceptance), login,
  own overview, patient detail with period and charts, manual glucose entry,
  doctor search and link management, atypical-day invitations, investigation
  conversations, notifications.
- Doctor flows: linked-patient list (active links only), patient detail,
  opening and closing investigations, notifications.
- Demo data comes from the UCI Diabetes dataset (historical dates around
  1990); manual entries land on current dates, so periods can mix both.
- A localized clinical PDF report per patient (pt-BR / en-US / es).

## Capabilities and Constraints

- Stack in place: FastAPI + SQLAlchemy/Alembic backend, React (Vite)
  frontend in `frontend-react/`, MySQL in deployment (Vercel serverless +
  managed MySQL), SQLite locally.
- Every user-facing string exists in `pt-BR` (primary), `en-US`, and `es`.
- The patient experience must work well on mobile (390 px wide and up)
  without horizontal scroll; the doctor experience is desktop-first.
- Roles are exclusive per account: an account is either a patient or a
  doctor.
- Terminology: "vínculo"/link (patient ↔ doctor), "questionamento"/
  investigation (conversation about an atypical day), "dias atípicos"/
  atypical days, "aguardando análise" (day recorded but not yet analysed).

## Brand Commitments

- Name: MyGlico. Assets: `frontend-react/public/img/myglico-logo.png`,
  `myglico-mark.svg`, and `myglico-logo-report.png` (PDF report).
- No clinical claims: MyGlico does not diagnose and is not a medical device.
  Indicators support the conversation; the clinical decision belongs to the
  doctor. Copy must never imply diagnosis or treatment advice.

## Evidence on Hand

- UCI Diabetes dataset (demo patients `data-01`… and demo doctor accounts).
- Generated provenance artifacts in `artifacts/provenance/`, presentations in
  `artifacts/presentations/`, final report in `artifacts/reports/`.
- No real patients, testimonials, clinical outcomes, or certifications exist;
  future work must not fabricate them.

## Product Principles

1. The patient comes first: their own data, in their own words, on their
   phone; research vocabulary stays out of their screens.
2. Consent is visible: who can see the patient's data, and why, is always
   one step away and revocable.
3. Support, never diagnose: indicators and atypical days open a
   conversation with the doctor; they do not judge the patient.
4. Traceable by design: every reading and collaboration event keeps its
   origin, and pending analysis is shown as pending, not as stable.

## Accessibility & Inclusion

WCAG 2.1 AA as the floor: contrast, visible focus, keyboard operation, and
readable text sizes, keeping in mind older patients and patients with low
vision.
