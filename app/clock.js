/** The wall clock and the pacing nudge.
 *
 *  The nudge compares the planned cumulative minute of the stop the visitor is
 *  currently looking at against the time actually elapsed. It is advice, not
 *  instruction, so it stays short and never scolds. */

/** Minutes of drift tolerated before the nudge says anything about it. */
const TOLERANCE = 3;
/** Beyond this there is no useful advice left to give but "enjoy yourself". */
const CAP = 20;

export const formatClock = (date) =>
  `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;

/**
 * @param {{started: number, now: number}} time
 * @param {{plannedAt: number, number: number}|null} stop the focused stop
 * @param {{plannedMinutes: number, stopCount: number}} route
 * @returns {{text: string, behind: boolean}}
 */
export function pacing(time, stop, route) {
  const finish = formatClock(new Date(time.started + route.plannedMinutes * 60000));
  const elapsed = (time.now - time.started) / 60000;

  if (elapsed < 1) return { text: `finish about ${finish}`, behind: false };

  const drift = stop ? stop.plannedAt - elapsed : 0;

  if (stop && stop.number === route.stopCount && drift > TOLERANCE) {
    return { text: 'take as long as you like', behind: false };
  }

  if (drift > TOLERANCE) {
    return { text: `${Math.min(CAP, Math.round(drift))} min in hand`, behind: false };
  }

  if (drift < -TOLERANCE) {
    return { text: `${Math.round(-drift)} min behind`, behind: true };
  }

  return { text: `on time · out by ${finish}`, behind: false };
}
