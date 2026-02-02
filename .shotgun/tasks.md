# Task Management: Redscribe Refactoring & Bug Fixes

## Instructions for AI Coding Agents

When working on these tasks:
1. **Focus on ONE stage at a time**, completing all tasks in that stage before moving to the next
2. **Mark each task complete** by replacing `[ ]` with `[X]` as you finish it
3. **Do NOT modify** any other content in this file unless explicitly instructed by the user
4. **Tasks without an `[X]` are not finished yet** - review the stage to see what remains

**Important notes:**
- Each task specifies the file(s) to modify and expected outcomes
- Acceptance criteria are provided for validation after implementation
- If a task fails, leave it unchecked and note the issue in comments (if needed)
- Dependencies are organized by stage - complete stages sequentially

**Graph ID for codebase tools:** `2a1b22f777a2`

---


## Agent Pipeline — Kolejność Uruchamiania

Poniższa tabela pokazuje, który plik agenta Claude Code odpowiada za które zadania. Uruchamiaj agentów po kolei, zgodnie z numeracją.

| # | Agent | Zadania (Sekcje w tasks.md) | Opis |
|---|-------|----------------------------|------|
| 1 | `CLAUDE-testwriter.md` 🧪 | Stage 1: sekcje 1.1-1.2 | Infrastruktura testowa + testy modułów core |
| 2 | `CLAUDE-backend.md` 🔧 | Stage 1: sekcja 1.3 | Naprawienie 5 krytycznych bugów |
| 3 | `CLAUDE-docs.md` 📚 | Stage 1: sekcja 1.4 | Aktualizacja zależności + walidacja Stage 1 |
| 4 | `CLAUDE-backend.md` 🔧 | Stage 2 (cały) | Separacja logiki biznesowej (TempFileManager, TranscriptionOrchestrator) |
| 5 | `CLAUDE-frontend.md` 🎨 | Stage 3 (cały) | Refaktoryzacja GUI (podział mega-metod) |
| 6 | `CLAUDE-backend.md` 🔧 / `CLAUDE-frontend.md` 🎨 | Stage 4: sekcje 4.1-4.3 | Type hints, eliminacja magic numbers, logging (backend na src/core/, frontend na src/gui/) |
| 7 | `CLAUDE-docs.md` 📚 | Stage 4: sekcje 4.4-4.5 | Dokumentacja (README, CHANGELOG) + testy końcowe |
| 8 | `CLAUDE-backend.md` 🔧 + `CLAUDE-frontend.md` 🎨 | Stage 5.1 | Parallel transcription (backend: ThreadPool, config; frontend: UI slider, progress) |
| 9 | `CLAUDE-backend.md` 🔧 + `CLAUDE-frontend.md` 🎨 | Stage 5.2 | Session persistence (backend: BatchStateManager; frontend: resume dialog) |
| 10 | `CLAUDE-backend.md` 🔧 | Stage 5.3 | Integracja równoległa + walidacja końcowa |
| 11 | `CLAUDE-backend.md` 🔧 | Stage 6: sekcje 6.1-6.3 | Batch History (BatchHistoryManager, AsyncBatchWriter, source verification) |
| 12 | `CLAUDE-frontend.md` 🎨 | Stage 6: sekcje 6.4-6.7 | History Tab + Smart Resume Dialog + Cancel UX + Settings Restore |
| 13 | `CLAUDE-testwriter.md` 🧪 | Stage 6: sekcja 6.8 | Testy Stage 6 (unit + integration + manual checklist) |

**Instrukcje dla użytkownika:**
1. Otwórz plik agenta (np. `CLAUDE-testwriter.md`)
2. Skopiuj zawartość do nowej sesji Claude Code / Cursor / Windsurf
3. Agent wykona zadania ze swojej sekcji i oznaczy je jako `[X]`
4. Przejdź do kolejnego agenta po zakończeniu wszystkich zadań z danej sekcji


---

## Stage 6: Batch History & Resume UX Overhaul

### Purpose
Enhance the batch resume system (from Stage 5) with persistent history, improved UX through a unified Batch Manager Tab, and robust lifecycle management.

### Prerequisites
- Stage 5 complete (parallel transcription and basic session persistence working)
- All tests passing
- Batch state persistence tested and stable

---

### Backend Tasks (Agent: CLAUDE-backend.md)

#### 6.1 Batch Lifecycle & History Storage

**6.1.1 Update BatchState Contract**

- [X] In `contracts/batch_state.py`, add `BatchStatus` enum: `ACTIVE | PAUSED | COMPLETED | ARCHIVED`
- [X] Add fields to `BatchState`: `status`, `completed_at`, `archived`
- [X] **Acceptance criteria:** Pydantic validation passes for new fields

**6.1.2 Implement BatchHistoryManager**

- [X] Create `src/utils/batch_history_manager.py` (replaces `BatchStateManager`)
- [X] Implement folder structure: `batches/active.json`, `batches/index.json`, `batches/{timestamp}_{batch_id}.json`
- [X] Implement methods:
  - `has_active_batch()`, `load_active_batch()`, `save_active_batch(state)`
  - `complete_batch(state)` - archives batch with timestamp filename
  - `pause_batch(state)`, `dismiss_active_batch()`
  - `load_batch_by_id(batch_id)`, `list_batches(status_filter=None)`
  - `delete_batch(batch_id)`, `cleanup_old_batches(days_threshold=30)`
- [X] Implement index file updates (add/update/remove entries)
- [X] **Acceptance criteria:** All methods working, index updates correctly, atomic writes verified

**6.1.3 Migrate Old Batch State**

- [X] Create `src/utils/migrate_batch_state.py`
- [X] Implement migration from old `batch_state.json` to new `batches/active.json`
- [X] Add migration call to `MainWindow.__init__()` (runs once on first startup)
- [X] **Acceptance criteria:** Old batch state migrated successfully, backup created

---

#### 6.2 Async Write Queue

**6.2.1 Implement BatchStateWriter**

- [X] Create `src/utils/batch_state_writer.py` (singleton pattern)
- [X] Implement background writer thread with `queue.Queue`
- [X] Implement throttling: max 1 write/second
- [X] Implement batching: consume multiple updates → single write
- [X] Implement methods: `schedule_write(state)`, `flush(timeout=5.0)`, `shutdown()`
- [X] **Acceptance criteria:** Writer thread starts/stops cleanly, throttling verified (1 write/sec max)

**6.2.2 Integrate BatchStateWriter in MainWindow**

- [X] In `MainWindow.__init__()`, create `self.batch_writer = BatchStateWriter()`
- [X] Update `_on_transcription_event()` to use `batch_writer.schedule_write(state)` instead of direct save
- [X] Update `_on_batch_complete()` to call `batch_writer.flush()` before archiving
- [X] **Acceptance criteria:** No UI lag during batch processing (1000 files), all state updates saved

---

#### 6.3 Source File Verification

**6.3.1 Implement verify_batch_files()**

- [X] In `BatchHistoryManager`, add `verify_batch_files(state) -> Dict[str, List[str]]`
- [X] Check source files exist (`Path(source_path).exists()`)
- [X] Check output files exist for completed status
- [X] Return dict with `missing_sources` and `missing_outputs` lists
- [X] **Acceptance criteria:** Method detects missing source and output files

**6.3.2 Integrate Verification in Resume**

- [X] Update `MainWindow._resume_batch()` to call `verify_batch_files(state)`
- [X] Mark missing sources as SKIPPED with error "Source file not found"
- [X] Mark missing outputs as PENDING for reprocessing
- [X] Show warning dialogs for missing files
- [X] **Acceptance criteria:** Missing files handled correctly, user notified

---

### Frontend Tasks (Agent: CLAUDE-frontend.md)

#### 6.4 Batch Manager Tab (Master-Detail UI)

**6.4.1 Create BatchManagerTab Class**

- [X] Create `src/gui/batch_manager_tab.py`
- [X] Implement master-detail layout (left: batch list, right: details panel)
- [X] Implement master panel:
  - Scrollable list with batch cards (date, status badge, format, files count, progress bar)
  - Filter dropdown: All / Active / Paused / Completed
  - Refresh button
- [X] Implement detail panel (hidden by default):
  - Header: batch_id, status badge, metadata (created, completed, duration)
  - Settings preview (readonly)
  - Progress summary (bar + counts)
  - Scrollable file list with checkboxes (pending/failed files only)
  - Action buttons: Resume All, Resume Selected, Re-run, Export CSV, Delete
- [X] **Acceptance criteria:** Tab displays correctly, clickable cards, detail panel shows/hides

**6.4.2 Implement Batch Card Rendering**

- [X] In `_create_batch_card(batch)`, render status badges with colors (● Active green, ⏸ Paused orange, ✓ Completed blue)
- [X] Add progress bar for incomplete batches (active/paused)
- [X] Add click handler to select batch and show details
- [X] Highlight selected batch card
- [X] **Acceptance criteria:** Cards render correctly, selection works, progress bars update

**6.4.3 Implement Detail Panel Population**

- [X] In `_populate_detail_panel(state)`, show batch metadata (ID, dates, duration)
- [X] Show settings (format, language, diarize, output_dir)
- [X] Show progress bar + summary (X completed, Y failed, Z pending)
- [X] Populate file list with checkboxes (max 20 files visible, scroll for more)
- [X] Enable/disable action buttons based on batch state
- [X] **Acceptance criteria:** Details accurate, checkboxes work, buttons enabled/disabled correctly

**6.4.4 Implement Batch Manager Actions**

- [X] Implement `_resume_all()` - call `MainWindow._resume_batch(state, selected_files=None)`
- [X] Implement `_resume_selected()` - get checked files, call `MainWindow._resume_batch(state, selected_files)`
- [X] Implement `_rerun_batch()` - placeholder dialog (future implementation)
- [X] Implement `_export_csv()` - save CSV with file list, status, errors
- [X] Implement `_delete_batch()` - call `BatchHistoryManager.delete_batch(batch_id)`
- [X] **Acceptance criteria:** Resume All/Selected works, CSV export correct, delete works

**6.4.5 Implement Auto-Refresh**

- [X] Add `_start_auto_refresh()` method with 2-second timer
- [X] Reload active batch detail panel if selected
- [X] Reload batch list if any active batches exist
- [X] **Acceptance criteria:** Live progress updates visible (every 2 seconds)

**6.4.6 Integrate Tab in MainWindow**

- [X] In `MainWindow._create_tabs()`, add Batch Manager tab
- [X] Pass references to `api_manager` and `main_window` (for resume calls)
- [X] **Acceptance criteria:** Tab appears in tabview, switches correctly

---

#### 6.5 Startup Notification (Replaces Smart Resume Dialog)

**6.5.1 Implement Lightweight Notification**

- [X] Update `MainWindow._check_pending_batch()` to show simple messagebox (not full dialog)
- [X] Message: "You have an incomplete batch. Created: [date], Completed: X, Remaining: Y. Open Batch Manager to resume?"
- [X] Buttons: [Yes] (switch to Batch Manager tab), [No] (pause batch, keep in history)
- [X] **Acceptance criteria:** Notification non-intrusive, "Open Batch Manager" switches to tab

---

#### 6.6 Cancel UX Improvement

**6.6.1 Update Progress Dialog Warning**

- [X] In `src/gui/progress_dialog.py`, change warning text:
  - BEFORE: "Do not close the window - this will cancel the transcription process"
  - AFTER: "Closing will pause the batch. You can resume later from Batch Manager tab."
- [X] **Acceptance criteria:** Warning text updated

**6.6.2 Add Post-Cancel Info Dialog**

- [X] In `MainWindow`, add `_on_batch_cancelled()` method
- [X] Show dialog: "Batch Paused. ✓ X completed, ○ Y remaining. You can resume later from Batch Manager tab."
- [X] Call `BatchHistoryManager.pause_batch(state)` on cancel
- [X] **Acceptance criteria:** Dialog appears after cancel, batch marked as paused

---

#### 6.7 Settings Restore (Verification)

**6.7.1 Verify Full Settings Restore**

- [X] In `MainWindow._resume_batch()`, verify ALL settings restored:
  - `output_format`, `output_dir`, `language`, `diarize`, `smart_format`, `max_concurrent_workers`
- [X] Add UI indicator: "⚠️ Resumed batch - settings restored from previous session"
- [X] **Acceptance criteria:** All settings restore correctly, indicator shown

---

### Testing Tasks (Agent: CLAUDE-testwriter.md)

#### 6.8 Unit Tests

**6.8.1 Test BatchHistoryManager**

- [X] Create `tests/test_batch_history_manager.py`
- [X] Test batch lifecycle: active → paused → completed
- [X] Test index updates (add/update/remove)
- [X] Test auto-cleanup (batches >30 days)
- [X] Test atomic writes (no corruption)
- [X] **Acceptance criteria:** 90%+ coverage, all lifecycle transitions tested

**6.8.2 Test BatchStateWriter**

- [X] Create `tests/test_batch_state_writer.py`
- [X] Test async write queue (schedule + flush)
- [X] Test throttling (max 1 write/sec)
- [X] Test batching (multiple updates → single write)
- [X] Test graceful shutdown
- [X] **Acceptance criteria:** 85%+ coverage, throttling verified

**6.8.3 Test Frontend Components**

- [X] Create `tests/test_batch_manager_tab.py` (with mocks)
- [X] Test batch card rendering
- [X] Test detail panel population
- [X] Test action buttons (resume, export, delete)
- [X] **Acceptance criteria:** Key UI methods tested (mocked GUI)

---

#### 6.9 Integration Tests

**6.9.1 Test E2E Resume Flow**

- [X] Create `tests/test_batch_lifecycle_integration.py`
- [X] Test: Create batch → cancel → resume from Batch Manager → complete
- [X] Test: Selective resume (uncheck some files)
- [X] Test: Missing source files handling
- [X] Test: Missing output files handling
- [X] **Acceptance criteria:** All E2E scenarios pass

---

#### 6.10 Manual Testing

**6.10.1 Manual Test Checklist**

- [ ] Start batch of 20 files → cancel after 10 → verify paused in Batch Manager
- [ ] Resume all → verify only 10 files processed
- [ ] Start batch → cancel → restart app → click "Open Batch Manager" → verify tab opens
- [ ] Delete 3 source files mid-batch → resume → verify skipped
- [ ] Delete 2 output files mid-batch → resume → verify reprocessed
- [ ] Export CSV → verify data correct
- [ ] Delete batch from history → verify removed
- [ ] Create batch 35 days ago (manual date edit) → run cleanup → verify deleted
- [ ] Large batch (1000 files) → verify async writes don't lag UI
- [ ] Test live progress updates (every 2 seconds) in Batch Manager

---

### Success Criteria

- ✅ **Batch Lifecycle:** Clear states (active/paused/completed/archived)
- ✅ **Persistent History:** Completed batches archived (not deleted)
- ✅ **Batch Manager Tab:** Master-detail layout working, live updates, all actions functional
- ✅ **Startup Notification:** Lightweight popup, non-intrusive, opens Batch Manager on "Yes"
- ✅ **Cancel UX:** User understands batch is paused (not lost)
- ✅ **Settings Restore:** ALL settings restored correctly
- ✅ **Async Writes:** No UI lag (1 write/sec max)
- ✅ **Source Verification:** Missing files detected and handled
- ✅ **Auto-Cleanup:** Old batches removed automatically
- ✅ **CSV Export:** Correct data export
- ✅ **Migration:** Old batch_state.json migrated successfully
- ✅ **Tests:** 85%+ coverage for new components

**Performance targets:**
- Batch Manager tab loads 100 batches in <500ms
- Detail panel opens in <200ms
- Async writes don't cause UI lag (1000 file batch)

---

### Files Created

**Backend:**
- `src/utils/batch_history_manager.py` - Batch history management
- `src/utils/batch_state_writer.py` - Async write queue
- `src/utils/migrate_batch_state.py` - Migration helper
- `contracts/batch_state.py` - Updated contract with BatchStatus enum

**Frontend:**
- `src/gui/batch_manager_tab.py` - Batch Manager tab (master-detail UI)

**Tests:**
- `tests/test_batch_history_manager.py` - Unit tests
- `tests/test_batch_state_writer.py` - Async writer tests
- `tests/test_batch_manager_tab.py` - Tab tests
- `tests/test_batch_lifecycle_integration.py` - E2E integration tests

---

### Files Modified

**Backend:**
- `src/gui/main_window.py` - Integrate BatchHistoryManager, BatchStateWriter, startup notification, resume methods

**Frontend:**
- `src/gui/progress_dialog.py` - Update cancel warning text

**Config:**
- `config.py` - Add batch cleanup settings (if needed)

---

### Risks & Mitigations

**Risk:** Migration from old batch_state.json breaks existing batches  
**Mitigation:** Migration helper backs up old file, only runs once, preserves state on failure

**Risk:** Async writes cause data loss on crash  
**Mitigation:** Flush pending writes before batch completion, atomic writes (tempfile + os.replace)

**Risk:** Large batch history (>1000 batches) slows Batch Manager  
**Mitigation:** Index file for fast lookup, lazy load details on click

**Risk:** User confusion with Batch Manager (too many options)  
**Mitigation:** Clear defaults ("Resume All"), help text, live progress updates

**Risk:** Source file verification adds latency  
**Mitigation:** Run in background, show progress if >50 files
