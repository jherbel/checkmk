#!/usr/bin/env python3
# Copyright (C) 2023 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from __future__ import annotations

import contextlib
import dataclasses
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Self

import pytest
import requests
from pydantic import BaseModel

from tests.testlib.site import Site

from cmk.utils.version import __version__, parse_check_mk_version

NUMBER_OF_EXTENSIONS_CHECKED = 150


CURRENTLY_UNDER_TEST = (
    "https://exchange.checkmk.com/api/packages/download/375/robotmk.v1.4.1-cmk2.mkp",
    "https://exchange.checkmk.com/api/packages/download/261/sslcertificates-8.8.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/309/ceph-11.17.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/321/SIGNL4-2.1.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/184/mikrotik-2.4.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/426/MSTeams-2.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/362/yum-2.4.3.mkp",
    "https://exchange.checkmk.com/api/packages/download/244/rspamd-1.4.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/161/kentix_devices-3.0.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/12/apcaccess-5.2.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/370/wireguard-1.5.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/319/hpsa-8.4.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/503/cve_2021_44228_log4j_cmk20.mkp",
    "https://exchange.checkmk.com/api/packages/download/181/memcached-5.7.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/369/veeam_o365-2.6.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/36/check_mk_api-5.5.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/361/win_adsync-2.2.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/101/dovereplstat-4.3.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/510/hpe_ilo-4.0.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/209/netifaces-7.0.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/170/lsbrelease-5.7.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/427/vsan-2.2.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/307/amavis-6.1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/468/check_snmp_metric-0.4.3.mkp",
    "https://exchange.checkmk.com/api/packages/download/332/win_scheduled_task-2.4.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/467/check_snmp-0.5.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/379/proxmox_provisioned-1.3.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/652/redfish-2.2.19.mkp",
    "https://exchange.checkmk.com/api/packages/download/77/cpufreq-2.3.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/418/acgateway-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/112/entropy_avail-5.2.3.mkp",
    "https://exchange.checkmk.com/api/packages/download/91/dell_sc-3.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/89/dell_omsa-3.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/590/pure-1.4.7.mkp",
    "https://exchange.checkmk.com/api/packages/download/371/esendex-2.4.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/333/winnfs-1.1.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/176/mailman_queues-5.2.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/14/apt-3.4.4.mkp",
    "https://exchange.checkmk.com/api/packages/download/145/icpraid-5.2.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/316/fail2ban-1.3.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/416/data2label-2.3.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/390/msexch_database_size-1.2.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/234/querx_webtherm-1.2.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/225/perfcalc-6.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/536/fileconnector-3.4.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/200/mysql_status-4.0.4.mkp",
    "https://exchange.checkmk.com/api/packages/download/134/gamatronic-1.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/334/php_fpm-0.20.mkp",
    "https://exchange.checkmk.com/api/packages/download/263/ssllabs-3.1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/341/qnap-1.4.5.mkp",
    "https://exchange.checkmk.com/api/packages/download/483/ABAS_Licenses-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/146/imap-3.0.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/404/telegram_notifications-2.0.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/320/postgres_replication-1.2.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/622/Nextcloud-2.5.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/337/qemu-2.0.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/478/fail2ban-1.9.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/534/dell_idrac_redfish-1.8.mkp",
    "https://exchange.checkmk.com/api/packages/download/342/ups_alarms-1.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/411/mirth-1.3.mkp",
    "https://exchange.checkmk.com/api/packages/download/509/lenovo_xclarity-2.7.mkp",
    "https://exchange.checkmk.com/api/packages/download/449/telegram_notify.mkp",
    "https://exchange.checkmk.com/api/packages/download/330/export_view-1.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/400/veeamcc_tenant-0.4c.mkp",
    "https://exchange.checkmk.com/api/packages/download/403/access_logs-1.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/324/huawei_wlc-1.0.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/378/emcunity-2.2.4.mkp",
    "https://exchange.checkmk.com/api/packages/download/339/EnterpriseAlert-1.5.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/420/rki_covid-1.1.3.mkp",
    "https://exchange.checkmk.com/api/packages/download/19/aufs-4.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/269/systemd-0.6.mkp",
    "https://exchange.checkmk.com/api/packages/download/422/mk_filehandler_bakery-0.3.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/279/veeamagent-1.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/284/webinject-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/490/nvidia-gpu-2.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/242/ricoh_used-1.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/560/dell_os10_chassis-1.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/3/adsl_line-1.4.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/346/smseagle-2.0.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/405/jb_fls-1.0.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/142/huawei-2.3.mkp",
    "https://exchange.checkmk.com/api/packages/download/238/raritan_pdu_outlets-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/358/proxmox_qemu_backup-1.3.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/512/unifi-2.2.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/423/jenkinsjobs-1.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/535/vcsa7_health_status-3.0.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/604/nut-2.0.4.mkp",
    "https://exchange.checkmk.com/api/packages/download/365/cisco_sb_fans-2.0.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/443/language-pack_japanese-1.3.mkp",
    "https://exchange.checkmk.com/api/packages/download/650/telematik_konnektor-1.2.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/281/VMware_VCSA_Services_HealthStatus_API_Monitoring-1.0.3.mkp",
    "https://exchange.checkmk.com/api/packages/download/46/cisco_bgp_peer-20180525.v.0.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/520/netapp_eseries-3.0.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/2/act-mkeventd-1.4.0p31.mkp",
    "https://exchange.checkmk.com/api/packages/download/197/mysql_performance-1.0.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/544/msteams-1.2.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/506/spit_defender_state-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/97/dir_size-1.1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/518/pihole_special_agent-1.0.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/391/webchecks-57.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/257/sonicwall-1.4.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/559/nextcloud-1.2.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/336/puppet_agent-1.0.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/18/aspsms-1.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/325/net_backup-1.0.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/489/telegram_bulk-1.0.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/425/cisco_bgp_peer.mkp",
    "https://exchange.checkmk.com/api/packages/download/609/btrfs_health-1.0.16.mkp",
    "https://exchange.checkmk.com/api/packages/download/50/cisco_inv_lldp-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/519/unifi_controller-0.83.mkp",
    "https://exchange.checkmk.com/api/packages/download/669/mshpc_jobs_and_nodes-1.0.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/103/dynamicscrm-0.4.mkp",
    "https://exchange.checkmk.com/api/packages/download/683/nutanix_prism-5.0.7.mkp",
    "https://exchange.checkmk.com/api/packages/download/469/bgp_peer.mkp",
    "https://exchange.checkmk.com/api/packages/download/447/language-pack_french-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/21/backupexec_job-1.6.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/268/synology-nas-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/133/freebox-v6-2.3.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/474/hello_world-0.1.3.mkp",
    "https://exchange.checkmk.com/api/packages/download/5/agent_ntnx-4.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/267/sync_check_multi-1.3.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/245/sap_hana-1.9.8.mkp",
    "https://exchange.checkmk.com/api/packages/download/104/ecallch-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/275/uname-2.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/163/last_windows_update-1.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/187/mongodb-1.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/236/Radius-0.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/318/fortigate_ipsec_p1-1.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/421/dell_storage-0.6.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/153/jenkins-0.3.mkp",
    "https://exchange.checkmk.com/api/packages/download/49/cisco_inv_cdp-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/159/kemplb-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/128/filehandles-3.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/681/Mailcow-1.2.0.mkp",
    "https://exchange.checkmk.com/api/packages/download/628/powerscale-2.1.4.mkp",
    "https://exchange.checkmk.com/api/packages/download/595/arista-1.0.4.mkp",
    "https://exchange.checkmk.com/api/packages/download/335/a10_loadbalancer-1.0.2.mkp",
    "https://exchange.checkmk.com/api/packages/download/444/language-pack_spanish-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/171/lvm-2.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/448/language-pack_dutch-1.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/406/snia_sml-2.0.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/291/windows_os_info-2.3.mkp",
    "https://exchange.checkmk.com/api/packages/download/452/urbackup_check-2.0.5.mkp",
    "https://exchange.checkmk.com/api/packages/download/571/openvpn_clients-0.4.1.mkp",
    "https://exchange.checkmk.com/api/packages/download/653/m365_service_health-1.2.1.mkp",
)


class _ExtensionName(str):
    ...


@dataclasses.dataclass(frozen=True, kw_only=True)
class _ImportErrors:
    base_errors: set[str] = dataclasses.field(default_factory=set)
    gui_errors: set[str] = dataclasses.field(default_factory=set)

    @classmethod
    def collect_from_site(cls, site: Site) -> Self:
        return cls(
            base_errors=set(
                json.loads(site.python_helper("_helper_failed_base_plugins.py").check_output())
            ),
            gui_errors=set(
                json.loads(site.python_helper("_helper_failed_gui_plugins.py").check_output())
            ),
        )


_DOWNLOAD_URL_BASE = "https://exchange.checkmk.com/api/packages/download/"


_EXPECTED_IMPORT_ERRORS: Mapping[str, _ImportErrors] = {
    "MSTeams-2.1.mkp": _ImportErrors(
        gui_errors={
            "wato/msteams: name 'socket' is not defined",
        }
    ),
    "cve_2021_44228_log4j_cmk20.mkp": _ImportErrors(
        gui_errors={
            "views/inv_cve_2021_22448_log4j: No module named 'cmk.gui.plugins.views.inventory'",
        },
    ),
}


def _get_tested_extensions() -> Iterable[tuple[str, str]]:
    return [(url, url.rsplit("/", 1)[-1]) for url in CURRENTLY_UNDER_TEST]


@pytest.mark.parametrize(
    "extension_download_url, name",
    [pytest.param(url, name, id=name) for url, name in _get_tested_extensions()],
)
def test_extension_compatibility(
    site: Site,
    extension_download_url: str,
    name: str,
) -> None:
    site.write_binary_file(
        extension_filename := "tmp.mkp",
        _download_extension(extension_download_url),
    )
    with _install_extension(site, site.resolve_path(Path(extension_filename))):
        encountered_errors = _ImportErrors.collect_from_site(site)
        expected_errors = _EXPECTED_IMPORT_ERRORS.get(name, _ImportErrors())

    assert encountered_errors.base_errors == expected_errors.base_errors
    assert encountered_errors.gui_errors == expected_errors.gui_errors


def _download_extension(url: str) -> bytes:
    try:
        response = requests.get(url)
    except requests.ConnectionError as e:
        raise pytest.skip(f"Encountered connection issues when attempting to download {url}") from e
    if not response.ok:
        raise pytest.skip(
            f"Got non-200 response when downloading {url}: {response.status_code}. Raw response: {response.text}"
        )
    try:
        # if the response is valid json, something went wrong (we still get HTTP 200 though ...)
        raise pytest.skip(f"Downloading {url} failed: {response.json()}")
    except ValueError:
        return response.content
    return response.content


@contextlib.contextmanager
def _install_extension(site: Site, path: Path) -> Iterator[_ExtensionName]:
    name = None
    try:
        name = _add_extension(site, path)
        _enable_extension(site, name)
        yield name
    finally:
        if name:
            _disable_extension(site, name)
            _remove_extension(site, name)


def _add_extension(site: Site, path: Path) -> _ExtensionName:
    return _ExtensionName(site.check_output(["mkp", "add", str(path)]).splitlines()[0].split()[0])


def _enable_extension(site: Site, name: str) -> None:
    site.check_output(["mkp", "enable", name])


def _disable_extension(site: Site, name: str) -> None:
    site.check_output(["mkp", "disable", name])


def _remove_extension(site: Site, name: str) -> None:
    site.check_output(["mkp", "remove", name])


def test_package_list_up_to_date() -> None:
    parsed_version = parse_check_mk_version(__version__)
    extensions = _compatible_extensions_sorted_by_n_downloads(parsed_version)

    # uncomment this to get output that you can paste into a spread sheet.
    # for extension in extensions:
    #     print(f"{extension.latest_version.link}\t{extension.downloads:5}")
    # assert False

    # the tested ones should be amongst the #M most popular ones.
    tested_unpopular = set(CURRENTLY_UNDER_TEST) - {
        e.latest_version.link for e in extensions[:NUMBER_OF_EXTENSIONS_CHECKED]
    }
    assert not tested_unpopular


def _compatible_extensions_sorted_by_n_downloads(parsed_version: int) -> list[_Extension]:
    return sorted(
        _compatible_extensions(parsed_version),
        key=lambda extension: extension.downloads,
        reverse=True,
    )


def _compatible_extensions(parsed_version: int) -> Iterator[_Extension]:
    response = requests.get("https://exchange.checkmk.com/api/packages/all")
    response.raise_for_status()
    all_packages_response = _ExchangeResponseAllPackages.model_validate(response.json())
    assert all_packages_response.success, "Querying packages from Checkmk exchange unsuccessful"
    for extension in all_packages_response.data.packages:
        try:
            min_version = parse_check_mk_version(extension.latest_version.min_version)
        except ValueError:
            continue
        if min_version < parsed_version:
            yield extension


class _LatestVersion(BaseModel, frozen=True):
    id: int
    min_version: str
    link: str


class _Extension(BaseModel, frozen=True):
    id: int
    latest_version: _LatestVersion
    downloads: int


class _ExchangeResponseAllPackagesData(BaseModel, frozen=True):
    packages: Sequence[_Extension]


class _ExchangeResponseAllPackages(BaseModel, frozen=True):
    success: bool
    data: _ExchangeResponseAllPackagesData
