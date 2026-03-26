type SettingsModalProps = {
  isOpen: boolean;
  onClose: () => void;
};

export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" onClick={(event) => event.stopPropagation()}>
        <h2>Sync settings</h2>
        <p>Choose how often the desktop app checks for updates.</p>
        <button type="button" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}