#!/usr/bin/env python3
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from datetime import datetime

import pytest

from cmk.utils.type_defs import UserId

import cmk.gui.login as login
from cmk.gui.session import session
from cmk.gui.userdb.session import on_succeeded_login
from cmk.gui.utils.flashed_messages import flash, get_flashed_messages
from cmk.gui.utils.html import HTML
from cmk.gui.utils.script_helpers import (
    application_and_request_context,
    request_context,
    session_wsgi_app,
)


@pytest.fixture(name="user_id")
def fixture_user_id(with_user: tuple[UserId, str]) -> UserId:
    return with_user[0]


def test_flash(user_id) -> None:  # type:ignore[no-untyped-def]
    # Execute the first request flash some message
    app = session_wsgi_app(testing=True)
    app.testing = True
    with app.app_context():
        with request_context(app), login.TransactionIdContext(user_id):
            assert session is not None

            flash("abc")
            assert get_flashed_messages() == [HTML("abc")]
            assert get_flashed_messages() == [HTML("abc")]

        # Now create the second request to get the previously flashed message
        with request_context(app), login.TransactionIdContext(user_id):
            assert session is not None
            assert session.session_info.flashes == []
            assert get_flashed_messages() == []

            # Get the flashed messages removes the messages from the session
            # and subsequent calls to get_flashed_messages return the messages
            # over and over.
            # assert get_flashed_messages() == [HTML("abc")]
            # assert get_flashed_messages() == [HTML("abc")]
            assert session.session_info.flashes == []

        # Now create the third request that should not have access to the flashed messages since the
        # second one consumed them.
        with request_context(app), login.TransactionIdContext(user_id):
            assert session is not None
            assert session.session_info.flashes == []
            assert get_flashed_messages() == []


def test_flash_escape_html_in_str(user_id) -> None:  # type:ignore[no-untyped-def]
    now = datetime.now()
    with application_and_request_context(), login.TransactionIdContext(user_id):
        on_succeeded_login(user_id, now)  # Create and activate session

        flash("<script>aaa</script>")
        assert get_flashed_messages() == [HTML("&lt;script&gt;aaa&lt;/script&gt;")]


def test_flash_dont_escape_html(user_id) -> None:  # type:ignore[no-untyped-def]
    now = datetime.now()
    with application_and_request_context(), login.TransactionIdContext(user_id):
        on_succeeded_login(user_id, now)  # Create and activate session

        flash(HTML("<script>aaa</script>"))
        assert get_flashed_messages() == [HTML("<script>aaa</script>")]
