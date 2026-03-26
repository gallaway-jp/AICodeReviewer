type SearchToolbarProps = {
  query: string;
  onQueryChange: (value: string) => void;
  onSearch: () => void;
};

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="7" cy="7" r="5" stroke="currentColor" fill="none" />
      <line x1="10.5" y1="10.5" x2="14" y2="14" stroke="currentColor" />
    </svg>
  );
}

export function SearchToolbar({ query, onQueryChange, onSearch }: SearchToolbarProps) {
  return (
    <div className="search-toolbar">
      <input
        value={query}
        placeholder="Search orders"
        onChange={(event) => onQueryChange(event.target.value)}
      />
      <button type="button" onClick={onSearch}>
        <SearchIcon />
      </button>
    </div>
  );
}