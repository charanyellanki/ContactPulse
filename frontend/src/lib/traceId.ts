/** Trace ID generation and validation.
 *
 * The trace ID is the unifying primitive between the Customer Experience and
 * Operator Console surfaces (CLAUDE.md §6). Every CE conversation issues one;
 * the OC drill-down looks up by it.
 */

export function generateTraceId(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 8);
  return `trc_${ts}_${rand}`;
}

export function isTraceId(value: string): boolean {
  return /^trc_[a-z0-9_]+$/i.test(value);
}
