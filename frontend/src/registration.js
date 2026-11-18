// Keep the displayed US date format independent of the browser's locale.
// Only the existing ISO date contract is sent to the backend.
export function birthDateToISO(value) {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value.trim());
  if (!match) return null;
  const [, month, day, year] = match;
  if (Number(year) < 1) return null;
  const date = new Date(0);
  date.setUTCFullYear(Number(year), Number(month) - 1, Number(day));
  if (
    date.getUTCFullYear() !== Number(year) ||
    date.getUTCMonth() !== Number(month) - 1 ||
    date.getUTCDate() !== Number(day)
  ) return null;
  return `${year}-${month}-${day}`;
}
