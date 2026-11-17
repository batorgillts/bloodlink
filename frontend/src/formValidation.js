import { birthDateToISO } from "./registration";

export function isoToUS(value) {
  if (!value) return "";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return match ? `${match[2]}/${match[3]}/${match[1]}` : value;
}

export function localDateTimeToISO(value) {
  const match = /^(\d{2}\/\d{2}\/\d{4}) (\d{2}):(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const iso = birthDateToISO(match[1]);
  const hour = Number(match[2]);
  const minute = Number(match[3]);
  if (!iso || hour > 23 || minute > 59) return null;
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(0);
  date.setFullYear(year, month - 1, day);
  date.setHours(hour, minute, 0, 0);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 ||
      date.getDate() !== day || date.getHours() !== hour || date.getMinutes() !== minute) return null;
  return date.toISOString();
}

export function fieldError(input) {
  const rules = input.dataset;
  const value = input.value;
  if (rules.required === "true" && !value.trim()) return "This field is required.";
  if (!value) return "";
  if (rules.fieldType === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
    return "Enter a valid email address, such as name@example.com.";
  }
  if (rules.minLength && value.length < Number(rules.minLength)) return `Use at least ${rules.minLength} characters.`;
  if (rules.maxLength && value.length > Number(rules.maxLength)) return `Use no more than ${rules.maxLength} characters.`;
  if (rules.pattern && !new RegExp(`^(?:${rules.pattern})$`).test(value)) {
    return rules.pattern === "[0-9]{10}" ? "Enter exactly 10 digits." : "Enter a value in the required format.";
  }
  if (rules.fieldType === "number") {
    const number = Number(value);
    if (!value.trim() || !Number.isFinite(number)) return "Enter a valid number.";
    if (rules.min !== undefined && number < Number(rules.min)) return `Enter a value of ${rules.min} or greater.`;
    if (rules.max !== undefined && number > Number(rules.max)) return `Enter a value of ${rules.max} or less.`;
    if (rules.step === "1" && !Number.isInteger(number)) return "Enter a whole number.";
  }
  if (rules.fieldType === "date" && !birthDateToISO(value)) return "Enter a valid date in MM/DD/YYYY format.";
  if (rules.fieldType === "datetime-local" && !localDateTimeToISO(value)) return "Enter a valid date and time in MM/DD/YYYY HH:mm format (24-hour time).";
  return "";
}
