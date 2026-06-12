/**
 * Parse a datetime string coming from the backend.
 *
 * The backend stores UTC values (datetime.utcnow()) on naive SQLAlchemy
 * DateTime columns, and Pydantic serializes them as ISO strings WITHOUT
 * a timezone marker (e.g. "2026-06-06T15:13:00.939875"). Browsers' Date
 * constructor treats such strings as LOCAL time, which is wrong — they
 * are UTC. Append the missing Z so the Date object correctly maps to
 * the user's local zone for display.
 */
export function parseBackendDate(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const hasTz = /[+-]\d{2}:?\d{2}$|Z$/.test(iso)
  return new Date(hasTz ? iso : iso + 'Z')
}
