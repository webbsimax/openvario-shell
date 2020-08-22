import asyncio
import os
from pathlib import Path
from typing import AsyncIterable

import pytest

from ovshell import testing
from ovshell.api import OpenVarioShell
from ovshell_core.sysinfo import SystemInfoImpl

ETC_OS_RELEASE_CONTENT = """ID="ovlinux"
NAME="OpenVario Linux (for OpenVario Flight Computer)"
VERSION="12345 (ov-test)"
VERSION_ID="12345"
PRETTY_NAME="OpenVario Linux (for OpenVario Flight Computer) 12345 (ov-test)"
"""

OPKG_LIST_INSTALLED_OUTPUT = """
xcsoar-maps-alps - 0.1-r3
xcsoar-maps-default - 0.1-r1
xcsoar-menu - 0.1-r3
xcsoar-profiles - 0.1-r1
xcsoar-testing - git-r11
xcsoar - 6.8.14
zap-console-fonts - 2.3-r0
"""


class TestSystemInfoImpl:
    @pytest.mark.asyncio
    async def test_get_openvario_version(
        self, ovshell: testing.OpenVarioShellStub
    ) -> None:
        # GIVEN
        sysinfo = SystemInfoImpl(ovshell.os)
        etcpath = Path(ovshell.os.path("//")) / "etc"
        etcpath.mkdir(parents=True)
        with open(etcpath / "os-release", "w") as f:
            f.write(ETC_OS_RELEASE_CONTENT)

        # WHEN
        ver = await sysinfo.get_openvario_version()

        # THEN
        assert ver == "12345 (ov-test)"

    @pytest.mark.asyncio
    async def test_get_installed_package_version_simple(
        self, ovshell: testing.OpenVarioShellStub
    ) -> None:
        # GIVEN
        sysinfo = SystemInfoImpl(ovshell.os)
        ovshell.os.stub_expect_run(0, stdout=OPKG_LIST_INSTALLED_OUTPUT.encode())

        # WHEN
        ver = await sysinfo.get_installed_package_version("xcsoar")

        # THEN
        assert ver == "6.8.14"

    @pytest.mark.asyncio
    async def test_get_installed_package_version_concurrent(
        self, ovshell: testing.OpenVarioShellStub
    ) -> None:
        # GIVEN
        sysinfo = SystemInfoImpl(ovshell.os)
        ovshell.os.stub_expect_run(0, stdout=OPKG_LIST_INSTALLED_OUTPUT.encode())

        # WHEN
        done, _ = await asyncio.wait(
            [
                sysinfo.get_installed_package_version("xcsoar"),
                sysinfo.get_installed_package_version("xcsoar-menu"),
            ]
        )

        # THEN
        assert len(done) == 2
        res = {task.result() for task in done}
        assert res == {"6.8.14", "0.1-r3"}

        # opkg is run only once
        assert ovshell.get_stub_log() == [
            "OS: Running //usr/bin/opkg list-installed",
        ]

    @pytest.mark.asyncio
    async def test_get_kernel_version(
        self, ovshell: testing.OpenVarioShellStub
    ) -> None:
        # GIVEN
        sysinfo = SystemInfoImpl(ovshell.os)
        # WHEN
        ver = await sysinfo.get_kernel_version()
        # THEN
        assert ver is not None

    @pytest.mark.asyncio
    async def test_get_hostname(self, ovshell: testing.OpenVarioShellStub) -> None:
        # GIVEN
        sysinfo = SystemInfoImpl(ovshell.os)
        # WHEN
        ver = await sysinfo.get_hostname()
        # THEN
        assert ver is not None
