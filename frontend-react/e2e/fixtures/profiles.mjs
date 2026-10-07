// Synthetic E2E profiles required by the acceptance matrix:
//   patient A, patient B, doctor A and doctor B.
//
// Product decision (2026-10-07): a UserAccount holds exactly one role, so the
// former dual-role profile was removed; AUT-CA-19 / CSCW-CA-33 are "Não
// aplicável" in MATRIZ-ACEITE.md.
//
// Rules (AGENTS.md / PROMPT-ORCA.md):
//   * no plaintext password is ever written to a versioned file or log — each
//     profile gets a fresh random password at runtime (override the whole set
//     with MYGLICO_E2E_PASSWORD when a stable value is needed locally);
//   * e-mails use the reserved, non-routable namespace @e2e.myglico.invalid;
//   * CRM/UF values are synthetic test data and never a real registration.
//
// Every test gets its own profile set (unique e-mail and CRM per test), so
// tests never collide on the unique e-mail / CRM+UF indexes of the shared
// E2E database. Within one test the same key always maps to the same
// identity (used on purpose by the duplicate-registration scenario).
import { randomBytes } from "node:crypto";

const RUN_ID = (
  process.env.MYGLICO_E2E_RUN_ID || randomBytes(4).toString("hex")
).toLowerCase();

const EMAIL_DOMAIN = "e2e.myglico.invalid";

let sequence = 0;

export function runtimePassword(prefix = "E2E") {
  if (process.env.MYGLICO_E2E_PASSWORD) return process.env.MYGLICO_E2E_PASSWORD;
  return `${prefix}-${randomBytes(12).toString("base64url")}`;
}

const TEMPLATES = {
  patientA: { roles: ["patient"], local: "patient-a", prefix: "E2E-A", display_name: "Paciente A (E2E)" },
  patientB: { roles: ["patient"], local: "patient-b", prefix: "E2E-B", display_name: "Paciente B (E2E)" },
  doctorA: { roles: ["doctor"], local: "medico-a", prefix: "E2E-MA", display_name: "Médico A (E2E)", uf: "SP" },
  doctorB: { roles: ["doctor"], local: "medico-b", prefix: "E2E-MB", display_name: "Médico B (E2E)", uf: "RJ" },
};

export const PROFILE_KEYS = Object.keys(TEMPLATES);

// A fresh, isolated set of identities. `tag` only makes e-mails readable.
export function createProfileSet(tag = "t") {
  sequence += 1;
  const scope = `${RUN_ID}-${sequence}`;
  const cache = new Map();
  return function profile(key) {
    if (!TEMPLATES[key]) throw new Error(`Unknown E2E profile: ${key}`);
    if (!cache.has(key)) {
      const template = TEMPLATES[key];
      const value = {
        key,
        roles: template.roles,
        email: `${template.local}.${tag}.${scope}@${EMAIL_DOMAIN}`,
        password: runtimePassword(template.prefix),
        display_name: template.display_name,
      };
      value.name = value.display_name;
      if (template.uf) {
        // 7-digit synthetic CRM, unique per run+test+profile.
        const seed = parseInt(randomBytes(3).toString("hex"), 16) % 9_000_000;
        value.crm = String(1_000_000 + seed);
        value.uf = template.uf;
      }
      cache.set(key, value);
    }
    return cache.get(key);
  };
}

export const RUN = RUN_ID;
