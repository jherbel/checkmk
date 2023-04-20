#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


def scan_genua(oid):
    return (
        "genuscreen" in oid(".1.3.6.1.2.1.1.1.0").lower()
        or "genubox" in oid(".1.3.6.1.2.1.1.1.0").lower()
        or "genucrypt" in oid(".1.3.6.1.2.1.1.1.0").lower()
    )
