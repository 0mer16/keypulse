# Third-party software

KeyPulse's own code is MIT licensed (see `LICENSE`). The Windows download also contains:

## OpenRGB 1.1 — GPL-2.0

KeyPulse ships an unmodified copy of [OpenRGB](https://openrgb.org) 1.1 in the `_internal/OpenRGB` folder.
KeyPulse runs it as a separate program and talks to it over OpenRGB's SDK network protocol.

- Licence: GNU General Public License v2.0 — full text in `_internal/OpenRGB/LICENSE.txt`
- Corresponding source code: attached to every KeyPulse GitHub release as `OpenRGB-1.1-source.zip`,
  and available at <https://codeberg.org/OpenRGB/OpenRGB/src/tag/release_1.1>
- Original binary: <https://codeberg.org/OpenRGB/OpenRGB/releases/tag/release_1.1>
  (`OpenRGB_1.1_Windows_64_8e16de2.zip`, SHA-256 `63291726C6FC84EB479EF2EE752E97E1187F6CE9C49FD27EEE40DED588A8172A`)

OpenRGB in turn includes Qt 6 (LGPL-3.0), hidapi, libusb (LGPL-2.1) and other components; see the OpenRGB source.

## Python libraries bundled in the app

| Library | Licence |
|---|---|
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | MIT |
| [NumPy](https://numpy.org) | BSD-3-Clause |
| [Pillow](https://python-pillow.org) | MIT-CMU (HPND) |
| Python / Tcl/Tk | PSF / Tcl licence |
| [PyInstaller](https://pyinstaller.org) bootloader | GPL-2.0 with bootloader exception |
