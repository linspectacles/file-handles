#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# LinSpectacles - Linux Inspection Suite
# Copyright (C) 2026 brunonlinespace
# GPL-3.0-or-later

APPLET_ID = "linspectacles-file-handles"
APPLET_NAME = "File Handles"
APPLET_VERSION = "0.0.8"
APPLET_AUTHOR = "brunonlinespace"
APPLET_EDITOR = "brunonlinespace"
APPLET_ORGANIZATION_ID = "linspectacles"
APPLET_ORGANIZATION_NAME = "LinSpectacles"
APPLET_ORGANIZATION_URL = "https://github.com/linspectacles/"
APPLET_REPOSITORY = "https://github.com/linspectacles/file-handles"

from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QUrl
from PyQt6.QtGui import QColor, QKeySequence, QPixmap, QShortcut, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ._support import BaseInspectorTab, export_records_dialog, metadata_font_qss


def _sources_text():
    return """File Handles is a read-only, system-wide procfs inspector. It does not enumerate per-process descriptors or scan filesystems.

File-description allocation
---------------------------
/proc/sys/fs/file-nr

field 1   Allocated file descriptions.
field 2   Allocated but unused descriptions (normally zero on Linux 2.6+).
field 3   Kernel-reported file-description maximum.

System and per-process ceilings
-------------------------------
/proc/sys/fs/file-max
/proc/sys/fs/nr_open

file-max  System-wide file-description allocation maximum.
nr_open   Kernel ceiling for a process's RLIMIT_NOFILE; each process's actual soft/hard limit may be lower.

Inode cache allocation and state
--------------------------------
/proc/sys/fs/inode-nr
/proc/sys/fs/inode-state

inode-nr fields 1–2   Allocated and free in-memory inode structures.
inode-state field 3    Preshrink indicator (where provided). Remaining fields are reserved.

Dentry cache state
------------------
/proc/sys/fs/dentry-state

field 1   Total allocated dentries.
field 2   Unused dentries on the reclaimable cache list.
field 3   Reclaim age limit in seconds.
field 4   Reclaim-request indicator (want_pages).
field 5   Unused negative dentries, where provided.
field 6   Reserved; not interpreted.

Derived values
--------------
Remaining file-description capacity = file-max − file-nr allocated.
File description limit usage = file-nr allocated / file-max × 100.
In-use cached inodes = inode-nr allocated − inode-nr free.
Active dentries (estimated) = total dentries − unused dentries.
Unused dentry share = unused dentries / total dentries × 100.

Interpretation limits
---------------------
In-memory inode counts are NOT the free inode capacity of a filesystem.
Cached dentries are NOT open file descriptors; negative dentries are cached failed path lookups.
The per-process descriptor ceiling is NOT any specific process's RLIMIT_NOFILE.
Procfs values are read sequentially and may change during acquisition.

Access model
------------
Ordinary-user, read-only procfs reads only. No scans of /proc/PID, privilege escalation, limit modifications, or background sampling.

Kernel interface reference
--------------------------
https://docs.kernel.org/admin-guide/sysctl/fs.html
"""


def _populate_sources_canvas(canvas):
    """Render existing procfs provenance in the Journal-style Sources palette.

    The source descriptions and their order are deliberately left intact. The
    plain-text dashed markers delimit headings but are not displayed; heading
    colour/weight now supplies that separation in the read-only canvas.
    """
    heading_format = QTextCharFormat()
    heading_format.setForeground(QColor("#9cdcfe"))
    heading_format.setFontWeight(600)

    value_format = QTextCharFormat()
    value_format.setForeground(QColor("#dcdcdc"))

    lines = _sources_text().splitlines()
    canvas.clear()
    cursor = canvas.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    for index, line in enumerate(lines):
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        is_section_heading = bool(line.strip() and next_line and set(next_line) == {"-"})
        is_underline = bool(line.strip() and set(line.strip()) == {"-"})
        if is_underline:
            continue
        is_source_line = line.startswith("/proc/")
        cursor.insertText(line + "\n", heading_format if (is_section_heading or is_source_line) else value_format)

    canvas.setTextCursor(cursor)
    canvas.moveCursor(QTextCursor.MoveOperation.Start)


def _record_details_plain_text(record):
    """Single metadata representation shared by the pane and optional export."""
    lines = [
        "--- File Handle / Inode Allocation ---",
        f"Metric: {record.get('metric') or 'Not reported'}",
        f"Value: {record.get('value') or 'Not reported'}",
        f"Source: {record.get('source') or 'Not reported'}",
        f"Kind: {record.get('kind') or 'Not reported'}",
    ]
    fields = (
        ("--- TECHNICAL DETAILS ---", (
            ("Meaning", "meaning"),
            ("Unit", "unit"),
            ("Related readings", "related"),
        )),
        ("--- CALCULATION ---", (
            ("Formula", "formula"),
            ("Inputs", "inputs"),
        )),
        ("--- INTERPRETATION LIMITS ---", (
            ("Limitations", "limitations"),
        )),
    )
    for heading, entries in fields:
        present = [(label, str(record.get(key) or "")) for label, key in entries if record.get(key)]
        if present:
            lines.extend(("", heading))
            lines.extend(f"{label}: {value}" for label, value in present)
    return "\n".join(lines)


def _collect_file_handle_records(read_text=None):
    """Acquire system-wide procfs counters once per source; no process traversal."""
    if read_text is None:
        read_text = lambda path: Path(path).read_text(encoding="utf-8")

    records = []
    notes = []
    primary_state = "observed"
    values = {}

    def read_fields(path, minimum):
        nonlocal primary_state
        try:
            words = read_text(path).strip().split()
            if len(words) < minimum:
                raise ValueError(f"expected at least {minimum} fields, got {len(words)}")
            fields = [int(word) for word in words]
            if any(number < 0 for number in fields):
                raise ValueError("negative counter encountered")
            return fields
        except (FileNotFoundError, PermissionError, ValueError, OSError) as exc:
            notes.append(f"{path}: {exc}")
            if path == "/proc/sys/fs/file-nr":
                primary_state = (
                    "unavailable" if isinstance(exc, FileNotFoundError)
                    else "restricted" if isinstance(exc, PermissionError)
                    else "error"
                )
        except Exception as exc:
            notes.append(f"{path}: {exc}")
            if path == "/proc/sys/fs/file-nr":
                primary_state = "error"
        return None

    def add(metric, value, source, kind, meaning, *, unit="Count", related="", formula="", inputs="", limitations=""):
        records.append({
            "metric": metric,
            "value": value if isinstance(value, str) else f"{value:,}",
            "source": source,
            "kind": kind,
            "category": kind,
            "meaning": meaning,
            "unit": unit,
            "related": related,
            "formula": formula,
            "inputs": inputs,
            "limitations": limitations,
        })

    file_nr = read_fields("/proc/sys/fs/file-nr", 3)
    if file_nr:
        allocated, unused, nr_max = file_nr[:3]
        values.update(allocated=allocated, unused=unused, nr_max=nr_max)
        add("Allocated file descriptions", allocated,
            "/proc/sys/fs/file-nr field 1", "Reported",
            "Kernel-allocated system-wide file descriptions (struct file objects).",
            related=f"Unused allocated descriptions: {unused:,}; file-nr maximum: {nr_max:,}.",
            limitations="Not the count of per-process file descriptors; multiple descriptors may share a file description.")
        add("file-nr field 2", unused,
            "/proc/sys/fs/file-nr field 2", "Reported",
            "Allocated but unused file descriptions reported in the second kernel field.",
            related=f"Allocated descriptions: {allocated:,}.",
            limitations="On Linux 2.6 and later this field normally remains zero because the kernel frees unused file descriptions; zero is not an error.")
        add("file-nr reported maximum", nr_max,
            "/proc/sys/fs/file-nr field 3", "Reported",
            "File-description allocation maximum reported in the same file-nr snapshot.",
            related=f"Allocated descriptions: {allocated:,}.",
            limitations="Read separately from file-max; the values can differ if settings change during acquisition.")

    file_max = read_fields("/proc/sys/fs/file-max", 1)
    if file_max:
        maximum = file_max[0]
        values["file_max"] = maximum
        add("System file description maximum", maximum,
            "/proc/sys/fs/file-max", "Reported",
            "System-wide upper limit on allocated file descriptions.",
            related=(f"Current allocated: {values['allocated']:,}; file-nr reported maximum: {values['nr_max']:,}."
                     if 'allocated' in values else "Current allocated: unavailable."),
            limitations="This is a system-wide allocation limit, not a process's open-file limit.")

    if 'allocated' in values and 'file_max' in values:
        allocated = values['allocated']
        maximum = values['file_max']
        remaining = maximum - allocated
        add("Remaining file-description capacity", remaining,
            "file-max − file-nr field 1", "Derived",
            "Arithmetic difference between the system-wide maximum and allocated file descriptions.",
            related=f"Allocated descriptions: {allocated:,}; system maximum: {maximum:,}.",
            formula="file-max − allocated", inputs=f"{maximum:,} − {allocated:,} = {remaining:,}",
            limitations="A negative value means the sampled allocation exceeds the sampled maximum; values are not an atomic snapshot.")
        if maximum > 0:
            pct = allocated / maximum * 100.0
            add("File description limit usage", f"{pct:.6f}%",
                "allocated / file-max × 100", "Derived",
                "Share of the configured system-wide file-description maximum currently allocated.",
                unit="Percent", related=f"Remaining arithmetic capacity: {remaining:,}.",
                formula="allocated / file-max × 100",
                inputs=f"{allocated:,} / {maximum:,} × 100 = {pct:.6f}%",
                limitations="Not per-process descriptor utilization; sampled counters may change during acquisition.")
        else:
            notes.append("file-max is zero; usage percentage is undefined")

    nr_open = read_fields("/proc/sys/fs/nr_open", 1)
    if nr_open:
        add("Per-process descriptor ceiling", nr_open[0],
            "/proc/sys/fs/nr_open", "Reported",
            "Kernel upper bound for a process's RLIMIT_NOFILE hard limit.",
            limitations="Not an actual process's soft or hard limit. Actual limits may be lower; no processes were inspected.")

    inode = read_fields("/proc/sys/fs/inode-nr", 2)
    if inode:
        total, free = inode[:2]
        values.update(inode_total=total, inode_free=free)
        add("Allocated inodes", total,
            "/proc/sys/fs/inode-nr field 1", "Reported",
            "Allocated in-memory inode structures across the kernel.",
            related=f"Free cached inode structures: {free:,}.",
            limitations="This is kernel inode-cache state, not total filesystem inode capacity.")
        add("Free inodes", free,
            "/proc/sys/fs/inode-nr field 2", "Reported",
            "Free in-memory inode structures retained in the inode cache.",
            related=f"Allocated cached inode structures: {total:,}.",
            limitations="Not free inodes on any mounted filesystem; filesystem free inode counts require filesystem-specific data.")
        if total >= free:
            used = total - free
            add("In-use cached inodes", used,
                "inode-nr field 1 − field 2", "Derived",
                "Allocated inode-cache structures not counted as free by inode-nr.",
                related=f"Allocated: {total:,}; free cached: {free:,}.",
                formula="allocated inodes − free inodes",
                inputs=f"{total:,} − {free:,} = {used:,}",
                limitations="This is an in-memory cache statistic, not a filesystem space or inode-capacity statistic.")
        else:
            notes.append("inode-nr free count exceeds allocated count; derived in-use count omitted")

    inode_state = read_fields("/proc/sys/fs/inode-state", 3)
    if inode_state:
        preshrink = inode_state[2]
        add("Inode preshrink indicator", preshrink,
            "/proc/sys/fs/inode-state field 3", "Reported",
            "Kernel inode-cache preshrink/pruning indicator.",
            related=f"inode-state allocated: {inode_state[0]:,}; inode-state free: {inode_state[1]:,}.",
            limitations="Nonzero is a kernel pruning signal, not evidence of filesystem inode exhaustion; trailing inode-state fields are reserved.")

    dentry = read_fields("/proc/sys/fs/dentry-state", 4)
    if dentry:
        total, unused, age, want_pages = dentry[:4]
        related = f"Total: {total:,}; unused: {unused:,}; age limit: {age:,} s; reclaim request: {want_pages:,}."
        add("Allocated dentries", total,
            "/proc/sys/fs/dentry-state field 1", "Reported",
            "Allocated directory-entry cache objects, both active and unused.",
            related=related,
            limitations="Dentries represent pathname lookup cache entries; they are not file descriptors or disk directory entries.")
        add("Unused dentries", unused,
            "/proc/sys/fs/dentry-state field 2", "Reported",
            "Unused dentry cache objects kept for potential reuse/reclaim.",
            related=related,
            limitations="Unused does not mean unused filesystem inodes or free disk capacity.")
        add("Dentry reclaim age limit", age,
            "/proc/sys/fs/dentry-state field 3", "Reported",
            "Kernel-reported age threshold for reclaiming dentry cache entries when memory is short.",
            unit="Seconds", related=related,
            limitations="A cache-reclamation parameter, not the age of every cached dentry.")
        add("Dentry reclaim request", want_pages,
            "/proc/sys/fs/dentry-state field 4", "Reported",
            "Kernel want_pages indicator associated with dentry-cache pruning.",
            unit="Kernel indicator", related=related,
            limitations="A nonzero value reports a reclaim request; it is not a count of filesystem-free pages.")
        if len(dentry) >= 5:
            negative = dentry[4]
            add("Unused negative dentries", negative,
                "/proc/sys/fs/dentry-state field 5", "Reported",
                "Unused cached negative pathname lookups (names without an associated file).",
                related=f"Unused dentries: {unused:,}; total dentries: {total:,}.",
                limitations="A subset of unused dentries; not a count of missing files on the filesystem.")
        if total >= unused:
            active = total - unused
            add("Active dentries (estimated)", active,
                "dentry-state field 1 − field 2", "Derived",
                "Allocated dentries minus those the kernel classifies as unused.",
                related=f"Total dentries: {total:,}; unused dentries: {unused:,}.",
                formula="allocated dentries − unused dentries",
                inputs=f"{total:,} − {unused:,} = {active:,}",
                limitations="Arithmetic estimate from kernel cache counters; not an inventory of active pathname objects.")
            if total > 0:
                share = unused / total * 100.0
                add("Unused dentry share", f"{share:.6f}%",
                    "unused dentries / total dentries × 100", "Derived",
                    "Fraction of allocated dentries currently reported as unused.",
                    unit="Percent", related=f"Total: {total:,}; unused: {unused:,}.",
                    formula="unused dentries / allocated dentries × 100",
                    inputs=f"{unused:,} / {total:,} × 100 = {share:.6f}%",
                    limitations="A dcache composition ratio, not an inode- or file-description utilization percentage.")
        else:
            notes.append("dentry-state unused count exceeds total; derived dentry counts omitted")

    return records, notes, primary_state


class FileHandlesOptionsDialog(QDialog):
    """Established LinSpectacles Options treatment for File Handles."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("Options — File Handles")
        self.resize(980, 720)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # Appearance
        appearance_page = QWidget()
        appearance_layout = QVBoxLayout(appearance_page)
        appearance_layout.setContentsMargins(12, 12, 12, 12)
        appearance_layout.setSpacing(10)

        appearance_heading = QLabel("Metadata display")
        heading_font = appearance_heading.font()
        heading_font.setBold(True)
        appearance_heading.setFont(heading_font)
        appearance_layout.addWidget(appearance_heading)

        appearance_note = QLabel(
            "Choose how the inventory and Metadata Details panes are arranged. "
            "This File Handles setting is remembered."
        )
        appearance_note.setWordWrap(True)
        appearance_layout.addWidget(appearance_note)

        layout_row = QHBoxLayout()
        layout_row.addWidget(QLabel("Record details layout:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["Horizontal", "Vertical"])
        self.layout_combo.setCurrentText(
            "Vertical" if owner.details_orientation == "vertical" else "Horizontal"
        )
        self.layout_combo.currentTextChanged.connect(self._layout_changed)
        layout_row.addWidget(self.layout_combo)
        layout_row.addStretch(1)
        appearance_layout.addLayout(layout_row)

        self.show_metadata_panel = QCheckBox("Show Metadata Details panel (F3)")
        self.show_metadata_panel.setChecked(owner.metadata_panel_visible)
        self.show_metadata_panel.toggled.connect(
            lambda checked: owner.set_metadata_panel_visible(bool(checked), persist=True)
        )
        appearance_layout.addWidget(self.show_metadata_panel)

        shortcut_note = QLabel(
            "Shortcuts: F3 hides/restores Metadata Details; Shift+F5 refreshes the "
            "file-handle inventory; Ctrl+L toggles Horizontal/Vertical; "
            "Ctrl+/ opens Options."
        )
        shortcut_note.setWordWrap(True)
        appearance_layout.addWidget(shortcut_note)
        appearance_layout.addStretch(1)
        tabs.addTab(appearance_page, "Appearance")

        # Sources
        sources_page = QWidget()
        sources_layout = QVBoxLayout(sources_page)
        sources_layout.setContentsMargins(12, 12, 12, 12)
        sources_layout.setSpacing(10)

        sources_heading = QLabel("Data Sources")
        sources_heading_font = sources_heading.font()
        sources_heading_font.setBold(True)
        sources_heading_font.setPointSize(max(sources_heading_font.pointSize(), 11))
        sources_heading.setFont(sources_heading_font)
        sources_layout.addWidget(sources_heading)

        sources_note = QLabel("Linux procfs interfaces used for read-only, system-wide file-description and cache inspection.")
        sources_note.setWordWrap(True)
        sources_layout.addWidget(sources_note)

        sources_text = QTextEdit()
        sources_text.setReadOnly(True)
        sources_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        chosen_font = getattr(owner, "_metadata_font", None)
        if chosen_font is not None:
            sources_text.setFont(chosen_font)
            sources_text.document().setDefaultFont(chosen_font)
            sources_text.setCurrentFont(chosen_font)
            font_rule = metadata_font_qss(chosen_font)
        else:
            font_rule = ""
        sources_text.setStyleSheet(
            "QTextEdit { background-color: #151719; color: #dcdcdc; border: 1px solid #333333; "
            f"{font_rule} "
            "}"
        )
        _populate_sources_canvas(sources_text)
        sources_layout.addWidget(sources_text, 1)
        tabs.addTab(sources_page, "Sources")

        # Export
        export_page = QWidget()
        export_layout = QVBoxLayout(export_page)
        export_layout.setContentsMargins(12, 12, 12, 12)
        export_layout.setSpacing(10)

        export_heading = QLabel("Export details")
        export_heading_font = export_heading.font()
        export_heading_font.setBold(True)
        export_heading.setFont(export_heading_font)
        export_layout.addWidget(export_heading)

        export_note = QLabel("Select the File Handles details to include in the export.")
        export_note.setWordWrap(True)
        export_layout.addWidget(export_note)

        self.export_metric = QCheckBox("Metric")
        self.export_value = QCheckBox("Value")
        self.export_source = QCheckBox("Source")
        self.export_kind = QCheckBox("Kind")
        self.export_metadata = QCheckBox("Metadata Details")

        for checkbox in (
            self.export_metric,
            self.export_value,
            self.export_source,
            self.export_kind,
        ):
            checkbox.setChecked(True)
        self.export_metadata.setChecked(False)

        for checkbox in (
            self.export_metric,
            self.export_value,
            self.export_source,
            self.export_kind,
            self.export_metadata,
        ):
            export_layout.addWidget(checkbox)

        export_layout.addStretch(1)
        export_row = QHBoxLayout()
        export_row.addStretch(1)
        export_button = QPushButton("Export...")
        export_button.clicked.connect(self._export_selected)
        export_row.addWidget(export_button)
        export_layout.addLayout(export_row)
        tabs.addTab(export_page, "Export")

        # About
        about_page = QWidget()
        about_layout = QVBoxLayout(about_page)
        about_layout.setContentsMargins(24, 20, 24, 18)
        about_layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(112, 112)
        icon_path = Path(__file__).resolve().parent / "icon.png"
        if icon_path.is_file():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                icon_label.setPixmap(
                    pixmap.scaled(
                        112,
                        112,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        about_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        name = QLabel("<h2 style='margin:0'>File Handles</h2>")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(name)

        version = QLabel(f"Version {APPLET_VERSION}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(version)

        slogan = QLabel("<b>Expose. Explore. Explain.</b>")
        slogan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(slogan)

        description = QLabel(
            "A read-only LinSpectacles applet for inspecting system-wide Linux "
            "file descriptions, limits, inode-cache and dentry-cache state from procfs."
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(description)

        details = QLabel(
            "<b>Build:</b> Standalone LinSpectacles applet<br>"
            f"<b>Organisation ID:</b> <a href='{APPLET_ORGANIZATION_URL}'>{APPLET_ORGANIZATION_ID}</a><br>"
            f"<b>Applet ID:</b> {APPLET_ID}"
        )
        details.setWordWrap(True)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(details)

        copyright_label = QLabel(
            "Copyright © 2026 "
            "<a href='https://github.com/brunonlinespace'>brunonlinespace</a>"
        )
        copyright_label.setOpenExternalLinks(True)
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(copyright_label)

        license_label = QLabel("Licensed under GNU GPLv3 or later.")
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(license_label)

        readme_url = QUrl.fromLocalFile(
            str(Path(__file__).resolve().parent.parent / "README.md")
        ).toString()
        license_url = QUrl.fromLocalFile(
            str(Path(__file__).resolve().parent.parent / "LICENSE")
        ).toString()
        links = QLabel(
            f"<a href='{readme_url}'>README</a> "
            "&nbsp;·&nbsp; "
            f"<a href='{license_url}'>License</a> "
            "&nbsp;·&nbsp; "
            f"<a href='{APPLET_REPOSITORY}'>Repository</a>"
        )
        links.setOpenExternalLinks(True)
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(links)
        about_layout.addStretch(1)
        tabs.addTab(about_page, "About")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _layout_changed(self, text):
        self.owner.set_details_orientation(str(text).strip().lower(), persist=True)

    def _export_selected(self):
        selected = []
        if self.export_metric.isChecked():
            selected.append(("metric", "Metric", 260, "left"))
        if self.export_value.isChecked():
            selected.append(("value", "Value", 180, "right"))
        if self.export_source.isChecked():
            selected.append(("source", "Source", 260, "left"))
        if self.export_kind.isChecked():
            selected.append(("kind", "Kind", 120, "left"))
        if self.export_metadata.isChecked():
            selected.append(("metadata_details", "Metadata Details", 520, "left"))

        if not selected:
            QMessageBox.information(self, "Export", "Select at least one detail to export.")
            return

        records = []
        for record in self.owner.get_export_records():
            item = dict(record)
            if self.export_metadata.isChecked():
                item["metadata_details"] = _record_details_plain_text(record)
            records.append(item)

        if not records:
            QMessageBox.information(self, "Export", "There is no collected data to export.")
            return

        path = export_records_dialog(self, APPLET_NAME, records, columns=selected)
        if path is not None:
            self.owner.set_status(f"Exported data to {path}")


class FileHandlesTab(BaseInspectorTab):
    """Read-only global file-description and inode allocation inspector."""

    def __init__(self, parent=None):
        columns = [
            ("metric", "Metric", 260, "left"),
            ("value", "Value", 180, "right"),
            ("source", "Source", 260, "left"),
            ("kind", "Kind", 120, "left"),
        ]
        categories = ["All Categories", "Reported", "Derived"]
        super().__init__("Total File Handle Records", columns, categories, parent)
        self.export_title = APPLET_NAME

        self.search_entry.setPlaceholderText("Search file handle records...")
        self.category_label.setText("Kind:")

        self.details_orientation = "horizontal"
        self._load_details_orientation()
        stored_visibility = QSettings("brunonlinespace", "File Handles").value(
            "metadata_panel_visible", True
        )
        self.set_metadata_panel_visible(
            str(stored_visibility).strip().lower() not in {"0", "false", "no", "off"},
            persist=False,
        )

        self.export_btn.setText("Options...")
        try:
            self.export_btn.clicked.disconnect()
        except TypeError:
            pass
        self.export_btn.clicked.connect(self.show_options)
        self.export_btn.setEnabled(True)

        self._install_shortcuts()
        self.load_modules()

    def _install_shortcuts(self):
        self._shortcuts = []
        for sequence, handler in (
            ("F3", self.toggle_metadata_panel),
            ("Ctrl+L", self.toggle_details_orientation),
            ("Shift+F5", self.load_modules),
            ("Ctrl+/", self.show_options),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def set_metadata_panel_visible(self, visible, *, persist=True):
        self.metadata_panel_visible = bool(visible)
        details_panel = self.splitter.widget(1)
        if details_panel is not None:
            details_panel.setVisible(self.metadata_panel_visible)
        if persist:
            settings = QSettings("brunonlinespace", "File Handles")
            settings.setValue("metadata_panel_visible", self.metadata_panel_visible)
            settings.sync()

    def toggle_metadata_panel(self):
        self.set_metadata_panel_visible(not self.metadata_panel_visible, persist=True)

    def toggle_details_orientation(self):
        self.set_details_orientation(
            "vertical" if self.details_orientation == "horizontal" else "horizontal",
            persist=True,
        )

    def show_options(self):
        dialog = FileHandlesOptionsDialog(self)
        dialog.exec()

    def _load_details_orientation(self):
        settings = QSettings("brunonlinespace", "File Handles")
        orientation = str(
            settings.value("details_orientation", "horizontal") or "horizontal"
        ).lower()
        if orientation not in {"horizontal", "vertical"}:
            orientation = "horizontal"
        self.set_details_orientation(orientation, persist=False)

    def set_details_orientation(self, orientation, *, persist=True):
        orientation = str(orientation or "horizontal").lower()
        if orientation not in {"horizontal", "vertical"}:
            orientation = "horizontal"
        self.details_orientation = orientation

        details_panel = self.splitter.widget(1)
        details_layout = details_panel.layout() if details_panel is not None else None
        if orientation == "vertical":
            self.splitter.setOrientation(Qt.Orientation.Vertical)
            if details_layout is not None:
                details_layout.setContentsMargins(0, 8, 0, 0)
            self.splitter.setSizes([430, 330])
        else:
            self.splitter.setOrientation(Qt.Orientation.Horizontal)
            if details_layout is not None:
                details_layout.setContentsMargins(8, 0, 0, 0)
            self.splitter.setSizes([480, 700])

        if persist:
            settings = QSettings("brunonlinespace", "File Handles")
            settings.setValue("details_orientation", orientation)
            settings.sync()

    def _filtered_records(self):
        query = self.search_entry.text().strip().lower()
        selected_kind = self.category_dropdown.currentText()
        matches = []
        for record in self.modules_data:
            match_kind = (
                selected_kind == "All Categories"
                or record.get("category") == selected_kind
            )
            match_query = not query or any(
                query in str(value).lower()
                for key, value in record.items()
                if not str(key).startswith("_")
            )
            if match_kind and match_query:
                matches.append(record)
        return matches

    def filter_modules(self, *_):
        from PyQt6.QtWidgets import QTableWidgetItem

        query = self.search_entry.text().strip().lower()
        selected_kind = self.category_dropdown.currentText()
        matches = self._filtered_records()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(matches))

        for row, record in enumerate(matches):
            for column_index, (column_id, _label, _width, alignment) in enumerate(self.columns):
                display = str(record.get(column_id, ""))
                item = QTableWidgetItem(display)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record)
                if alignment == "right":
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                else:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row, column_index, item)

        self.export_btn.setEnabled(True)
        if query or selected_kind != "All Categories":
            self.filter_status_lbl.setText(
                f"(Showing {len(matches)} of {len(self.modules_data)} items)"
            )
        else:
            self.filter_status_lbl.clear()

    def load_modules(self):
        records, notes, state = _collect_file_handle_records()
        self.modules_data = records
        self.stats_label.setText(f"Total File Handle Records: {len(self.modules_data)}")
        self.filter_modules()

        if state != "observed":
            self.set_status(
                f"Loaded {len(records)} file/inode/dentry record(s); "
                f"the primary procfs source was {state}. {'; '.join(notes)}"
            )
        elif notes:
            self.set_status(
                f"Loaded {len(records)} file/inode/dentry record(s). " + "; ".join(notes)
            )
        else:
            reported = sum(1 for record in records if record.get("kind") == "Reported")
            derived = sum(1 for record in records if record.get("kind") == "Derived")
            self.set_status(
                f"Loaded {len(records)} file/inode/dentry record(s): "
                f"{reported} reported, {derived} derived."
            )

        if self.modules_data:
            self.table.selectRow(0)
        else:
            self.clear_info()
            self.append_info("--- File Handle / Inode Allocation ---\n")
            self.append_info("No file-handle, inode, or dentry records were available.\n")
            self._scroll_details_to_top()

    def on_module_select(self):
        record = self.current_record()
        if not record:
            return

        self.clear_info()
        self.append_info(_record_details_plain_text(record) + "\n")
        self._scroll_details_to_top()
        self.set_status(f"Inspecting {record.get('metric', 'file-handle metric')}.")

    def _scroll_details_to_top(self):
        cursor = self.info_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.info_text.setTextCursor(cursor)
        self.info_text.ensureCursorVisible()
        bar = self.info_text.verticalScrollBar()
        if bar is not None:
            bar.setValue(bar.minimum())


def create_applet(parent=None):
    return FileHandlesTab(parent=parent)


def run_standalone():
    import sys
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication, QMainWindow
    from ._support import STANDALONE_STYLESHEET

    app = QApplication(sys.argv)
    app.setApplicationName(APPLET_NAME)
    app.setOrganizationName(APPLET_ORGANIZATION_ID)

    icon_path = Path(__file__).resolve().parent / "icon.png"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    app.setStyleSheet(STANDALONE_STYLESHEET)

    window = QMainWindow()
    if icon_path.is_file():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.setWindowTitle(f"{APPLET_NAME} {APPLET_VERSION} — {APPLET_ORGANIZATION_NAME} Applet")
    window.resize(1200, 780)
    window.setCentralWidget(create_applet())
    window.show()
    return app.exec()
