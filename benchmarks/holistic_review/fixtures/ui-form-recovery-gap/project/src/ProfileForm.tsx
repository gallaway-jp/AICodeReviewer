import { useState } from "react";
import { validateProfile } from "./validators";

type Props = {
  saveProfile: (payload: { name: string; email: string }) => Promise<void>;
};

export function ProfileForm({ saveProfile }: Props) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("");

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const errors = validateProfile({ name, email });
    if (errors.length > 0) {
      setName("");
      setEmail("");
      setStatus("Profile could not be saved.");
      return;
    }

    await saveProfile({ name, email });
    setStatus("Saved.");
  }

  return (
    <form onSubmit={handleSubmit}>
      <label>
        Name
        <input value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        Email
        <input value={email} onChange={(event) => setEmail(event.target.value)} />
      </label>
      <button type="submit">Save profile</button>
      <p>{status}</p>
    </form>
  );
}
