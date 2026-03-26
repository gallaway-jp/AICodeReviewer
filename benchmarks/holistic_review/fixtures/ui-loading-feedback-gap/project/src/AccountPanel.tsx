import { useAccount } from "./useAccount";

type Props = {
  accountId: string;
};

export function AccountPanel({ accountId }: Props) {
  const { data, isLoading, error, refresh } = useAccount(accountId);

  if (!data) {
    return null;
  }

  return (
    <section>
      <header>
        <h2>{data.name}</h2>
        <button onClick={refresh}>Refresh</button>
      </header>
      <p>{data.email}</p>
    </section>
  );
}
