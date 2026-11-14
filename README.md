# File Handles

**Expose. Explore. Explain.**

File Handles is a read-only global Linux file-description and inode-allocation inspector using procfs.

Current release: **0.0.8**

Repository: <https://github.com/linspectacles/file-handles>

<p align="center">
  <a href="https://github.com/brunonlinespace/brunonlinespace/blob/main/linspectacles/file-handles.png">
    <img
      src="https://raw.githubusercontent.com/brunonlinespace/brunonlinespace/main/linspectacles/file-handles.png"
      alt="File Handles screenshot"
      width="900"
    >
  </a>
</p>

## What File Handles is

File Handles answers a focused question: **what global file-description and inode allocation values is the running kernel reporting?**

The applet reports information available from its documented Linux sources. Data that is unavailable, restricted, or not reported by those sources remains explicitly unavailable rather than being inferred.

## Highlights

- Allocated file-description information from `/proc/sys/fs/file-nr`.
- System file-description maximum from `/proc/sys/fs/file-max`.
- Allocated/free inode information from `/proc/sys/fs/inode-nr`.
- Derived file-description limit usage from the reported allocated count and `file-max`.
- Metadata keeps the procfs field origin visible rather than turning the values into a process-level handle list.

## Data sources and acquisition

- `/proc/sys/fs/file-nr`.
- `/proc/sys/fs/file-max`.
- `/proc/sys/fs/inode-nr`.

The applet uses those sources according to the acquisition paths implemented in this release. Optional tools or privileged helpers only affect the views/actions that explicitly use them; they are not treated as silent substitutes for unrelated sources.

## Interface

File Handles follows the LinSpectacles inventory + **Metadata Details** pattern where applicable: an acquired inventory remains separate from the details for the selected record, and search/filter controls operate on the data the applet has actually collected.

The applet's **Options** surface provides the presentation/source/about controls implemented by this release, together with export controls where present in the source. Applet-specific actions remain explicit rather than being folded into background collection.

## Read-only and scope boundaries

This is a global kernel allocation view, not a per-process open-file browser. The applet does not change kernel limits, close file descriptions or modify inode state.

## Running from source

The supplied source is directly runnable on Linux. The Python-side requirements are:

- Python 3.
- PyQt6 for the graphical interface.

Create a local virtual environment if you do not already have the required Python packages in the environment you want to use:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install PyQt6
python3 linspectacles_file_handles/standalone.py
```

Linux commands, procfs/sysfs interfaces, system services, or optional helpers mentioned in **Data sources and acquisition** are applet-specific runtime inputs. Data that is unavailable, restricted, or not reported by those sources remains explicitly unavailable rather than being inferred.

No RPM installation instructions are included in this README.

## LinSpectacles Hub

This applet can run independently, but it can also be installed and used inside **[LinSpectacles Hub](https://github.com/linspectacles/linspectacles-hub)**.

LinSpectacles Hub is the optional workbench for the LinSpectacles applet family. It provides shared applet discovery, navigation and management while each inspector remains independently runnable.

To install a portable or user applet through the Hub, open **Configuration... → Applets** and add the applet ZIP. Once discovered, the applet can be enabled and opened from the Hub navigation.

System-installed applets are discovered by the Hub from its system applet store and remain managed by the system package manager.

## Source layout and LinSpectacles integration

The applet source is contained in:

```text
linspectacles_file_handles/
├── __init__.py
├── standalone.py
├── LICENSE
├── applet.json
├── README.md
└── file_handles/
    ├── applet.py
    ├── _support.py
    └── icon.png
```

`applet.json` defines the applet's LinSpectacles identity and integration metadata. `standalone.py` provides direct standalone launching, while the applet entrypoint allows the same inspector to run inside LinSpectacles Hub.

## Configuration

Presentation and inspection preferences are persisted only through the settings mechanisms already implemented by the applet. Persisted UI state does not grant the applet permission to modify the inspected Linux subsystem.

## Scope

File Handles is intentionally specialist. Related Linux information that belongs to another LinSpectacles subsystem remains outside this applet rather than being inferred or duplicated here.

## License

GNU General Public License v3.0 or later. See [`LICENSE`](LICENSE).

## Links

- LinSpectacles organisation: <https://github.com/linspectacles/>
- LinSpectacles Hub: <https://github.com/linspectacles/linspectacles-hub>
- Repository: <https://github.com/linspectacles/file-handles>
- Issues: <https://github.com/linspectacles/file-handles/issues>

<p align="center">
  <a href="https://github.com/linspectacles/file-handles">
    <img
      src="file_handles/icon.png"
      alt="File Handles"
      width="256"
    >
  </a>
</p>
