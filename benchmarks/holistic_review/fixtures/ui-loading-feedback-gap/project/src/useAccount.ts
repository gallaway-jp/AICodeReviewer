type Account = {
  name: string;
  email: string;
};

type AccountState = {
  data: Account | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
};

export function useAccount(accountId: string): AccountState {
  void accountId;

  return {
    data: null,
    isLoading: true,
    error: null,
    refresh: () => {},
  };
}
