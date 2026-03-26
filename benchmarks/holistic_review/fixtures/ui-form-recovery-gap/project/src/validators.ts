export function validateProfile(payload: { name: string; email: string }): string[] {
  const errors: string[] = [];

  if (!payload.name.trim()) {
    errors.push("Name is required.");
  }

  if (!payload.email.includes("@")) {
    errors.push("Email must be valid.");
  }

  return errors;
}
