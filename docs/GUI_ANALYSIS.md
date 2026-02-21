# AICodeReviewer GUI — Code Analysis Report

**Date:** 2026-02-20  
**Scope:** `src/aicodereviewer/gui/app.py`, `src/aicodereviewer/gui/test_fixtures.py`,
`tools/manual_test_gui.py`

---

## 1  Confirmed Bugs

### 1.1 Dry-run crashes with `AssertionError` (Critical)
**File:** `app.py` — `_run_review` (~line 1277)

```python
client = None if dry_run else create_backend(backend_name)
...
assert client is not None          # ← always fails when dry_run=True
runner = AppRunner(client, ...)
```

`_start_dry_run` calls `_run_review(params, dry_run=True)`, so `client` is always `None`
at that point. The unconditional assert raises `AssertionError` every time the Dry Run
button is pressed.

**Fix:** Guard the assert and runner creation:
```python
if not dry_run:
    assert client is not None
    runner = AppRunner(client, scan_fn=scan_fn, backend_name=backend_name)
    result = runner.run(...)
else:
    result = AppRunner(None, scan_fn=scan_fn, backend_name=backend_name).run(
        **params, dry_run=True, ...)
```
Or redesign so `AppRunner` explicitly handles `dry_run=True` without a client.

---

### 1.2 Windows backslash normalization is broken (High)
**File:** `app.py` — `custom_scan_fn` inside `_run_review` (~line 1258)

```python
rel_norm = rel_path.replace("\\\\", "/") if rel_path else ""
```

`str.replace("\\\\", "/")` only matches the two-character sequence `\\` (a literal
double-backslash). On Windows, `Path.relative_to()` returns single forward or backward
slashes, so matched diff entries are never found and the entire diff-filter feature
silently produces an empty file list.

**Fix:**
```python
rel_norm = rel_path.replace("\\", "/") if rel_path else ""
```

---

### 1.3 `ai_fixed` status is missing from `_status_display` (High)
**File:** `app.py` — `_status_display` (~line 1438)

The `ReviewIssue.status` value `"ai_fixed"` is produced by the batch AI-Fix flow, and
`test_fixtures.py` uses it in sample data. It is not in the `_status_display` mapping:

```python
m = {
    "resolved",   "ignored", "skipped",
    "fixed",      "fix_failed",           # ← "ai_fixed" absent
}
```

Any card with `status == "ai_fixed"` displays as **Pending ●** in the wrong color.

**Fix:** Add the entry:
```python
"ai_fixed": ("gui.results.ai_fixed", "green"),
```
Add the matching i18n key to all locale files.

---

### 1.4 Non-pending cards lose their action buttons after exiting AI-Fix mode (High)
**File:** `app.py` — `_exit_ai_fix_mode` (~line 1694)

When restoring issue cards after AI-Fix mode, only `pending` issues get their View /
Resolve / Skip buttons re-gridded:

```python
if rec["issue"].status == "pending":
    rec["view_btn"].grid(...)
    rec["resolve_btn"].grid(...)
    rec["skip_btn"].grid(...)
```

Issues in `resolved`, `skipped`, `fix_failed`, or `ai_fixed` states lose the **View**
button permanently.

**Fix:** Always restore the **View** button regardless of status, and conditionally hide
the mutable action buttons (Resolve / Skip) based on status:
```python
# Always show View
rec["view_btn"].grid(row=2, column=2, padx=2, pady=(0, 4))
if rec["issue"].status == "pending":
    rec["resolve_btn"].grid(row=2, column=4, padx=2, pady=(0, 4))
    rec["skip_btn"].grid(row=2, column=5, padx=2, pady=(0, 4))
```

---

### 1.5 Settings tab reset uses a hardcoded English tab label (Medium)
**File:** `app.py` — `_reset_defaults` (~line 2257)

```python
for widget in self.tabs.tab("Settings").winfo_children():
```

`"Settings"` is the English translated value of `t("gui.tab.settings")`. When the UI
language is Japanese, `self.tabs.tab("Settings")` raises `_tkinter.TclError` because
the tab was created with the Japanese label.

**Fix:**
```python
for widget in self.tabs.tab(t("gui.tab.settings")).winfo_children():
```

---

### 1.6 Log handler accumulates on repeated `App` instantiation (Medium)
**File:** `app.py` — `_install_log_handler` (~line 290)

`_install_log_handler` appends a new `QueueLogHandler` to the root logger every time an
`App` instance is created. In automated test runs or any code that re-creates `App`, the
root logger grows unboundedly and duplicate log lines appear.

**Fix:** Remove the handler when the window is destroyed:
```python
def destroy(self):
    logging.getLogger().removeHandler(self._queue_handler)
    super().destroy()
```
And store the reference: `self._queue_handler = handler` in `_install_log_handler`.

---

### 1.7 `_manual_test_mode` attribute set externally is never read (Low)
**File:** `tools/manual_test_gui.py` (~line 63) and `app.py`

```python
app._manual_test_mode = True   # set in manual_test_gui.py
```

Nowhere in `app.py` is `self._manual_test_mode` tested; only `self._testing_mode`
(a constructor parameter) is used. The externally-set attribute is dead code and could
mislead future maintainers.

**Fix:** Remove the line from `manual_test_gui.py`, or add a check to `App.__init__`:
```python
self._testing_mode = testing_mode
```
and pass `testing_mode=True` directly (it already is).

---

### 1.8 Unused variable `_all_skipped` (Low)
**File:** `app.py` — `_update_bottom_buttons` (~line 1456)

```python
_all_skipped = all(c["issue"].status == "skipped" for c in self._issue_cards)
```

This value is computed but never referenced. Remove it or use it in an appropriate
conditional.

---

### 1.9 `FileSelector` scans files on the main thread (Medium)
**File:** `app.py` — `FileSelector._build_ui` (~line 162)

```python
files = scan_project(str(self.project_path))
```

`scan_project` performs a full directory walk on the GUI thread. For large projects this
blocks the Tkinter event loop, freezing the entire application until the scan completes.

**Fix:** Run the scan in a background thread and show a loading indicator while it
completes, then populate the tree asynchronously.

---

## 2  Design & Code Quality Issues

### 2.1 Duplicated health-check machinery (DRY violation)
`_auto_health_check` and `_check_backend_health` are nearly identical: both set up a
60-second `threading.Timer`, spawn the same `_worker` closure, and contain identical
`finally` / error paths. The only difference is that the automatic version shows a
dialog only on failure while the manual version always shows the dialog.

**Fix:** Extract a private `_run_health_check(backend_name, *, always_show_dialog: bool)`
method and call it from both.

---

### 2.2 Diff-preview toolbar lacks syntax highlight coloring
**File:** `app.py` — `_show_diff_preview` (~line 2025)

The comment in the code acknowledges the limitation:
```python
# Note: CTkTextbox doesn't support tags directly, so we use a simple approach
```
The unified diff is inserted as plain text with no coloring (added lines in green, removed
lines in red). This makes it hard to read.

**Fix:** Use a `tkinter.Text` widget (wrapped in a frame) instead of `CTkTextbox` for the
diff view. `tkinter.Text` supports named tags with `fg`/`bg` colors and allows the diff
to be properly color-coded.

---

### 2.3 Import inside tight loops / repeated widget callbacks
Several methods import modules inside deeply nested functions or loops:
- `custom_scan_fn` imports `parse_diff_file` and `get_diff_from_commits` on every call.
- `_show_batch_fix_popup._apply_selected` opens file handles inline with no context manager
  for the outer loop.

**Fix:** Hoist imports to the top of the method (or module) and ensure all file handles
are managed with `with` statements already in place — the inner `with open(...)` is fine;
the deferred imports are the concern.

---

### 2.4 `_issue_cards` uses plain `dict` — no type safety
Every element of `self._issue_cards` is a `dict[str, Any]`, meaning any typo (`"staus_lbl"`
instead of `"status_lbl"`) produces a silent `KeyError` at runtime rather than a type
error at development time.

**Fix:** Replace with a small `dataclass` or `TypedDict`:
```python
from typing import TypedDict
class IssueCard(TypedDict):
    issue: ReviewIssue
    card: Any
    status_lbl: Any
    view_btn: Any
    resolve_btn: Any
    skip_btn: Any
    fix_checkbox: Any
    fix_check_var: Any
    skip_frame: Any
    skip_entry: Any
    color: str
```

---

### 2.5 `_on_backend_changed` writes to disk on every radio-button click
**File:** `app.py` (~line 2200)

Switching backends silently calls `config.save()` immediately, which performs a full file
write. If the user is mid-edit in the Settings tab (with unsaved changes), the backend
change from the Review tab will overwrite the Settings tab's unsaved backend selection.

**Fix:** Defer the disk write to the existing "Save Settings" button path, or at minimum
keep the Review-tab selection in memory and only persist when `_save_settings` is called.

---

### 2.6 No validation feedback for numeric settings fields
The Settings tab accepts free-text for numeric fields (`batch_size`, `max_tokens`,
`timeout`, etc.) with no type checking. Entering `"abc"` is accepted silently by
`config.set_value` and will cause crashes later when the value is read as an integer.

**Fix:** Add a `_validate_numeric` helper that is called from `_save_settings` before
writing numeric fields, with a toast notification on invalid input.

---

### 2.7 `_show_toast` stacks overlapping notifications
Multiple rapid calls (e.g. quick validation failures) place all toast frames at the same
`rely=0.96` position, causing them to visually overlap.

**Fix:** Maintain a toast queue and vertically offset each subsequent toast, or dismiss
the previous toast before showing a new one.

---

### 2.8 Built-in editor has no "discard changes" confirmation
**File:** `app.py` — `_open_builtin_editor` (~line 1560)

The Cancel button calls `win.destroy()` unconditionally. If the user has typed edits,
they are silently discarded with no warning.

**Fix:**
```python
def _cancel():
    if text.get("0.0", "end").strip() != original_content.strip():
        if not messagebox.askyesno("Discard changes?",
                                   "You have unsaved changes. Discard them?"):
            return
    win.destroy()
```

---

### 2.9 Log tab has no export button
Users cannot save log output to a file. For bug reports this is significant.

**Fix:** Add a "Save Log…" button that opens a `filedialog.asksaveasfilename` and writes
`self.log_box.get("0.0", "end")`.

---

### 2.10 Tooltip window leaks on widget destroy
**File:** `app.py` — `_Tooltip._show` (~line 87)

If the parent widget is destroyed while the tooltip is visible, `self._tipwindow` is not
cleaned up and a `tkinter.TclError` may occur on the next `<Leave>` event.

**Fix:** Add a `<Destroy>` binding:
```python
widget.bind("<Destroy>", self._hide)
```

---

## 3  UX / Feature Improvements

| # | Area | Description |
|---|------|-------------|
| 3.1 | Results tab | Add a **filter bar** (by severity, status, type) to help navigate large result sets. |
| 3.2 | Results tab | Show the total issue count broken down by severity in the summary line. |
| 3.3 | Issue cards | Truncating `description` to 120 characters can lose important context; make this dynamic or configurable. |
| 3.4 | Keyboard shortcuts | `Ctrl+S` in Settings to save, `Ctrl+Enter` to start a review, `Ctrl+W` to close dialogs. |
| 3.5 | Review tab | Persist the selected-files list (`FileSelector` result) to config so it survives restarts. |
| 3.6 | Progress | Show a **time elapsed** counter next to the progress bar during long reviews. |
| 3.7 | Health check | Display a countdown next to the status label during the 60-second timeout. |
| 3.8 | Log tab | Add **log level filter** controls (DEBUG / INFO / WARNING / ERROR). |
| 3.9 | Diff preview | Implement true side-by-side split view (two `Text` widgets synchronized by scrollbar). |
| 3.10 | Session persistence | Add "Save Session / Load Session" for partially-reviewed issue sets. |

---

## 4  Testing Recommendations

1. **`test_fixtures.py`** covers severity × status combinations well, but `ai_fixed` cards
   should be explicitly tested for correct status label and color once Bug 1.3 is fixed.
2. Add an automated integration test (headless Tkinter) that clicks **Dry Run** and
   asserts no `AssertionError` is raised (covers Bug 1.1).
3. Add a parameterized test for `_status_display` against all known `.status` values to
   prevent future mapping omissions.
4. Add a unit test for `_reset_defaults` in Japanese locale to guard against Bug 1.5.

---

## 5  Priority Summary

| Priority | ID | Issue |
|----------|----|-------|
| 🔴 Critical | 1.1 | Dry-run always crashes (`AssertionError`) |
| 🔴 High | 1.2 | Diff-filter never matches files on Windows |
| 🔴 High | 1.3 | `ai_fixed` status renders incorrectly as pending |
| 🔴 High | 1.4 | Action buttons disappear after AI-Fix mode exit |
| 🟠 Medium | 1.5 | Settings reset crashes in non-English locale |
| 🟠 Medium | 1.6 | Log handler leak on repeated instantiation |
| 🟠 Medium | 1.9 | File selector blocks main thread on large projects |
| 🟡 Low | 1.7 | `_manual_test_mode` attribute is dead code |
| 🟡 Low | 1.8 | Unused `_all_skipped` variable |
| 🔵 Design | 2.1–2.9 | Code quality, DRY, type safety, UX hardening |
