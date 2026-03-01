"""Pytest configuration and shared fixtures."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def mock_tkinter_dialogs():
    """Auto-mock all tkinter file/message dialogs and blocking calls to prevent blocking in tests."""
    with patch('tkinter.filedialog.askopenfilename') as mock_open, \
         patch('tkinter.filedialog.asksaveasfilename') as mock_save, \
         patch('tkinter.filedialog.askdirectory') as mock_dir, \
         patch('tkinter.simpledialog.askstring') as mock_string, \
         patch('tkinter.messagebox.showinfo') as mock_info, \
         patch('tkinter.messagebox.showwarning') as mock_warn, \
         patch('tkinter.messagebox.showerror') as mock_err, \
         patch('tkinter.messagebox.askyesno') as mock_yesno, \
         patch('customtkinter.CTk.wait_window') as mock_wait_window:
        
        # Default return values
        mock_open.return_value = ""
        mock_save.return_value = ""
        mock_dir.return_value = ""
        mock_string.return_value = ""
        mock_info.return_value = None
        mock_warn.return_value = None
        mock_err.return_value = None
        mock_yesno.return_value = False
        mock_wait_window.return_value = None
        
        yield {
            'open': mock_open,
            'save': mock_save,
            'dir': mock_dir,
            'string': mock_string,
            'info': mock_info,
            'warn': mock_warn,
            'error': mock_err,
            'yesno': mock_yesno,
            'wait_window': mock_wait_window,
        }
