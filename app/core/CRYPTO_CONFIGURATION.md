# MyGlico backend cryptographic configuration

Set these variables in the backend runtime's secret manager. Do not commit key
values, put them in the frontend, or include them in logs. Keys are 32 random
bytes represented as exactly 64 hexadecimal characters.

| Variable | Purpose |
| --- | --- |
| `MYGLICO_ENCRYPTION_KEY_V1` | AES-256-GCM key for payloads marked version 1. |
| `MYGLICO_ENCRYPTION_KEY_V2` | Optional next AES-256-GCM key during key rotation. |
| `MYGLICO_ACTIVE_ENCRYPTION_KEY_VERSION` | Version used for new ciphertext; defaults to `1`. |
| `MYGLICO_LOOKUP_HMAC_KEY` | Separate HMAC-SHA256 key for blind equality indexes. |
| `MYGLICO_SESSION_TTL_HOURS` | Server-side browser session lifetime in hours; defaults to `12`. |

Field payloads contain a two-byte format marker, one-byte key version, fresh
12-byte nonce, and AES-GCM ciphertext with its authentication tag. Associated
data is `table:column:record_id`. Keep each old encryption key configured until
all payloads using that version have been re-encrypted. The blind-index key is
independent and should not be reused for encryption.

Email lookup values are not keys: email indexes use trimmed, lowercase
addresses. CRM + UF indexes preserve CRM internal punctuation and characters,
trim surrounding whitespace, uppercase both components, and encode the pair as
a compact JSON array before HMAC. This keeps serialization unambiguous while
avoiding destructive assumptions about CRM number formats.

The account password format uses scrypt with a fresh random salt and records
the work parameters in the encoded hash. Passwords are never reversibly
encrypted.

## Public UCI demonstration credentials

The explicit `scripts/import_uci_diabetes.py --provision-demo-accounts` mode is
an intentional public-dataset demonstration exception. New patient accounts
use `patient1@demo.myglico.invalid`, `patient2@demo.myglico.invalid`, and so on,
assigned in the stable first-provisioning order derived from
`PatientSourceLink.external_patient_code`. An assigned number is retained
across later imports. The single new demonstration doctor account uses
`doctor@demo.myglico.invalid`. Existing demo emails and password hashes are
never rewritten by a re-import. The password for every newly created account
in this mode is the literal `qwerty`; it is hashed with the configured adaptive
password hasher before storage. These public credentials are exclusive to the
UCI demonstration and must not be used for real accounts. Emails remain
encrypted at rest and are found through the separate blind HMAC index; the
importer never prints passwords. Legacy `.com` identities from earlier demo
provisioning are recognized for idempotent upgrades but are not assigned to
new demo accounts.

## Clinical fields and database visibility

Free-text `glucose_records.notes` is encrypted at rest with the same
AES-256-GCM/AAD mechanism as other sensitive text. The numeric
`glucose_mg_dl`, timestamp `measured_at`, categorical `context_label`, and
derived aggregate fields in `daily_indicators` and `daily_metrics_current`
remain queryable in plaintext. The analytics algorithm repeatedly groups and
calculates over every measurement; applying authenticated decryption row by row
would add substantial CPU cost and prevent efficient SQL aggregation/indexing.
UCI measurements are also from the published public dataset, while names and
free-text notes can contain directly identifying or sensitive information.
This is a documented data-minimization trade-off, not a claim that the numeric
clinical data is encrypted.

## Account role invariant

Each `UserAccount` is associated with at most one domain identity: a `Patient`
or a `Doctor`, never both. The same email cannot be registered again for a
second role; people using both roles must create separate accounts with
different email addresses. There is no API operation that attaches another
role to an existing account.

For an existing database, configure both `MYGLICO_ENCRYPTION_KEY_V1` and
`MYGLICO_LOOKUP_HMAC_KEY` before `alembic upgrade head`; the migration encrypts
legacy Patient name/email values before dropping the plaintext columns. An
empty database does not need the encryption keys just to create the schema.
Test migrations against an isolated SQLite database or a copy of the local
database, never against production as part of development validation.
