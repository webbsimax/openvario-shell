from typing import Callable, List, Optional, Dict, Any
import os
import asyncio
import shutil
from dataclasses import dataclass, asdict

import urwid

from ovshell import protocol
from ovshell import widget

USB_MOUNTPOINT = "//usb/usbstick"


@dataclass
class DownloadFilter:
    new: bool = True
    igc: bool = True
    nmea: bool = False

    def asdict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def fromdict(cls, state: Dict[str, Any]) -> "DownloadFilter":
        filt = cls()
        if "new" in state:
            filt.new = state["new"]
        if "igc" in state:
            filt.igc = state["igc"]
        if "nmea" in state:
            filt.nmea = state["nmea"]
        return filt


@dataclass
class FileInfo:
    name: str
    ftype: str
    size: int
    mtime: float
    downloaded: bool


class LogDownloaderApp(protocol.App):
    name = "download-logs"
    title = "Download Logs"
    description = "Download flight logs to USB storage"
    priority = 50

    def __init__(self, shell: protocol.OpenVarioShell):
        self.shell = shell

    def launch(self) -> None:
        act = LogDownloaderActivity(self.shell)
        self.shell.screen.push_activity(act)


class LogDownloaderActivity(protocol.Activity):
    def __init__(self, shell: protocol.OpenVarioShell):
        self.shell = shell
        xcsdir = shell.os.path(shell.settings.getstrict("xcsoar.home", str))
        mntdir = shell.os.path(USB_MOUNTPOINT)

        self.mountwatcher = AutomountWatcher(mntdir)

        filtstate = shell.settings.get("fileman.download-logs.filter", dict) or {}
        self.filter = DownloadFilter.fromdict(filtstate)
        self.downloader = Downloader(os.path.join(xcsdir, "logs"), mntdir, self.filter)

    def create(self) -> urwid.Widget:
        self._waiting_view = urwid.Filler(
            urwid.Text("Please insert USB storage", align="center"), "middle"
        )
        self._file_pile = urwid.Pile([])
        self._app_view = self._create_app_view()
        self.frame = urwid.Frame(
            self._waiting_view, header=widget.ActivityHeader("Download Flight Logs")
        )
        return self.frame

    def activate(self) -> None:
        self.mountwatcher.on_mount(self._mounted)
        self.mountwatcher.on_unmount(self._unmounted)
        self.shell.screen.spawn_task(self, self.mountwatcher.run())

    def _create_app_view(self) -> urwid.Widget:
        file_filter = self._make_filter()
        return urwid.Filler(
            urwid.Pile([file_filter, urwid.Divider(), self._file_pile]), "top"
        )

    def _mounted(self) -> None:
        self._populate_file_pile()
        self.frame.set_body(self._app_view)

    def _unmounted(self) -> None:
        self.frame.set_body(self._waiting_view)

    def _make_filter(self) -> urwid.Widget:
        options = urwid.GridFlow(
            [
                self._make_filter_checkbox("New logs", "new"),
                self._make_filter_checkbox("*.igc", "igc"),
                self._make_filter_checkbox("*.nmea", "nmea"),
            ],
            cell_width=12,
            h_sep=2,
            v_sep=1,
            align="left",
        )
        return urwid.LineBox(options, "Options", title_align="left")

    def _populate_file_pile(self):
        files = self.downloader.list_logs(self.filter)
        if files:
            file_items = [self._make_file_picker(de) for de in files]
        else:
            file_items = [urwid.Text(("remark", "No flight logs selected."))]
        self._file_pile.contents = [(w, ("pack", None)) for w in file_items]
        self._file_pile.focus_position = 0

    def _make_filter_checkbox(self, title: str, attr: str) -> urwid.Widget:
        checked = getattr(self.filter, attr)
        cb = urwid.CheckBox(title, checked)
        urwid.connect_signal(cb, "change", self._set_filter_option, user_args=[attr])
        return cb

    def _set_filter_option(self, attr: str, w: urwid.Widget, state: bool) -> None:
        setattr(self.filter, attr, state)
        self.shell.settings.set("fileman.download-logs.filter", self.filter.asdict())
        self.shell.settings.save()
        self._populate_file_pile()

    def _make_file_picker(self, fileinfo: FileInfo) -> urwid.Widget:
        statusw = urwid.Text("")
        cols = urwid.Columns(
            [
                ("weight", 4, urwid.Text(fileinfo.name)),
                ("weight", 1, urwid.Text(format_size(fileinfo.size))),
                ("weight", 1, statusw),
            ]
        )
        w = SelectableItem(cols)
        urwid.connect_signal(
            w, "click", self._file_clicked, user_args=[fileinfo, statusw]
        )
        return w

    def _file_clicked(self, fileinfo: FileInfo, statusw: urwid.Text, w: urwid.Widget):
        self.downloader.download(fileinfo)
        statusw.set_text(("success banner", " Done "))
        os.sync()


class AutomountWatcher:
    _mount_handlers: List[Callable[[], None]]
    _unmount_handlers: List[Callable[[], None]]

    def __init__(self, mountpoint: str) -> None:
        self._mountpoint = mountpoint
        self._mount_handlers = []
        self._unmount_handlers = []

    async def run(self) -> None:
        mounted = False
        while True:
            if os.path.exists(self._mountpoint):
                if not mounted:
                    self._handle_mount()
                mounted = True
            else:
                if mounted:
                    self._handle_unmount()
                mounted = False
            await asyncio.sleep(1)

    def on_mount(self, handler: Callable[[], None]) -> None:
        self._mount_handlers.append(handler)

    def on_unmount(self, handler: Callable[[], None]) -> None:
        self._unmount_handlers.append(handler)

    def _handle_mount(self) -> None:
        for handler in self._mount_handlers:
            handler()

    def _handle_unmount(self) -> None:
        for handler in self._unmount_handlers:
            handler()


class Downloader:
    """Object that handles file copying and listing"""

    def __init__(self, source_dir: str, mount_dir: str, filter: DownloadFilter) -> None:
        self.source_dir = source_dir
        self.mount_dir = mount_dir
        self.filter = filter

    def list_logs(self, filter: DownloadFilter) -> List[FileInfo]:
        if not os.path.exists(self.source_dir):
            return []
        res = []
        for entry in os.scandir(self.source_dir):
            _, fext = os.path.splitext(entry.name.lower())
            fileinfo = FileInfo(
                name=entry.name,
                ftype=fext,
                size=entry.stat().st_size,
                mtime=entry.stat().st_mtime,
                downloaded=False,
            )
            if self._matches(fileinfo, self.filter):
                res.append(fileinfo)
        return sorted(res, key=lambda fi: fi.mtime, reverse=True)

    def download(self, file: FileInfo) -> None:
        destdir = self._ensure_dest_dir()
        srcfile = os.path.join(self.source_dir, file.name)
        shutil.copy(srcfile, destdir)

    def _matches(self, fileinfo: FileInfo, filter: DownloadFilter) -> bool:
        ftypes = [".nmea" if filter.nmea else None, ".igc" if filter.igc else None]
        matches = fileinfo.ftype in ftypes
        if filter.new:
            matches = matches and not fileinfo.downloaded
        return matches

    def _ensure_dest_dir(self) -> str:
        assert os.path.exists(self.mount_dir)
        destdir = self._get_dest_dir()
        os.makedirs(destdir, exist_ok=True)
        return destdir

    def _get_dest_dir(self) -> str:
        return os.path.join(self.mount_dir, "logs")


class SelectableItem(urwid.WidgetWrap):
    signals = ["click"]

    def __init__(self, widget: urwid.Widget) -> None:
        wdg = urwid.AttrMap(widget, "li normal", "li focus")
        super().__init__(wdg)

    def selectable(self):
        return True

    def keypress(self, size, key: str) -> Optional[str]:
        if self._command_map[key] == "activate":
            self._emit("click")
            return None
        return key


def format_size(size: int) -> str:
    suffix = "B"
    fsize = float(size)
    for unit in ["", "Ki", "Mi", "Gi"]:
        if abs(fsize) < 1024.0:
            return "%3.1f%s%s" % (fsize, unit, suffix)
        fsize /= 1024.0
    return "%.1f%s%s" % (size, "Ti", suffix)