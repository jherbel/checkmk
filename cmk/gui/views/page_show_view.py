#!/usr/bin/env python3
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

"""Display a table view"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import chain
from typing import Any

import livestatus
from livestatus import SiteId

from cmk.utils.cpu_tracking import CPUTracker, Snapshot
from cmk.utils.site import omd_site
from cmk.utils.type_defs import UserId

import cmk.gui.log as log
import cmk.gui.visuals as visuals
from cmk.gui.config import active_config
from cmk.gui.ctx_stack import g
from cmk.gui.display_options import display_options
from cmk.gui.exceptions import MKMissingDataError, MKUserError
from cmk.gui.exporter import exporter_registry
from cmk.gui.htmllib.html import html
from cmk.gui.http import request
from cmk.gui.i18n import _
from cmk.gui.logged_in import user
from cmk.gui.page_menu import make_external_link, PageMenuEntry, PageMenuTopic
from cmk.gui.plugins.visuals.utils import Filter, get_livestatus_filter_headers
from cmk.gui.type_defs import (
    ColumnName,
    PainterParameters,
    Row,
    Rows,
    SorterName,
    SorterSpec,
    ViewSpec,
)
from cmk.gui.utils.urls import makeuri_contextless
from cmk.gui.view import View
from cmk.gui.view_renderer import ABCViewRenderer, GUIViewRenderer
from cmk.gui.views.data_source import data_source_registry

from . import availability
from .painter.v0.base import Cell, JoinCell
from .painter_options import PainterOptions
from .row_post_processing import post_process_rows
from .sorter import SorterEntry
from .store import get_all_views, get_permitted_views


def page_show_view() -> None:
    """Central entry point for the initial HTML page rendering of a view"""
    with CPUTracker() as page_view_tracker:
        view_name = request.get_ascii_input_mandatory("view_name", "")
        view_spec = visuals.get_permissioned_visual(
            view_name,
            request.get_validated_type_input(UserId, "owner"),
            "view",
            get_permitted_views(),
            get_all_views(),
        )
        _patch_view_context(view_spec)

        datasource = data_source_registry[view_spec["datasource"]]()
        context = visuals.active_context_from_request(datasource.infos, view_spec["context"])

        view = View(view_name, view_spec, context)
        view.row_limit = get_limit()

        view.only_sites = visuals.get_only_sites_from_context(context)

        view.user_sorters = get_user_sorters(view.spec["sorters"], view.row_cells)
        view.want_checkboxes = get_want_checkboxes()

        # Gather the page context which is needed for the "add to visual" popup menu
        # to add e.g. views to dashboards or reports
        visuals.set_page_context(context)

        # Need to be loaded before processing the painter_options below.
        # TODO: Make this dependency explicit
        display_options.load_from_html(request, html)

        painter_options = PainterOptions.get_instance()
        painter_options.load(view.name)
        painter_options.update_from_url(view.name, view.painter_options)
        process_view(GUIViewRenderer(view, show_buttons=True))

    _may_create_slow_view_log_entry(page_view_tracker, view)


def _may_create_slow_view_log_entry(page_view_tracker: CPUTracker, view: View) -> None:
    duration_threshold = active_config.slow_views_duration_threshold
    if page_view_tracker.duration.process.elapsed < duration_threshold:
        return

    logger = log.logger.getChild("slow-views")
    logger.debug(
        (
            "View name: %s, User: %s, Row limit: %s, Limit type: %s, URL variables: %s"
            ", View context: %s, Unfiltered rows: %s, Filtered rows: %s, Rows after limit: %s"
            ", Duration fetching rows: %s, Duration filtering rows: %s, Duration rendering view: %s"
            ", Rendering page exceeds %ss: %s"
        ),
        view.name,
        user.id,
        view.row_limit,
        # as in get_limit()
        request.var("limit", "soft"),
        [f"{k}={v}" for k, v in request.itervars() if k != "selection" and v != ""],
        view.context,
        view.process_tracking.amount_unfiltered_rows,
        view.process_tracking.amount_filtered_rows,
        view.process_tracking.amount_rows_after_limit,
        _format_snapshot_duration(view.process_tracking.duration_fetch_rows),
        _format_snapshot_duration(view.process_tracking.duration_filter_rows),
        _format_snapshot_duration(view.process_tracking.duration_view_render),
        duration_threshold,
        _format_snapshot_duration(page_view_tracker.duration),
    )


def _format_snapshot_duration(snapshot: Snapshot) -> str:
    return "%.2fs" % snapshot.process.elapsed


def _patch_view_context(view_spec: ViewSpec) -> None:
    """Apply some hacks that are needed because for some edge cases in the view / visuals / context
    imlementation"""
    # FIXME TODO HACK to make grouping single contextes possible on host/service infos
    # Is hopefully cleaned up soon.
    # This is also somehow connected to the datasource.link_filters hack hat has been created for
    # linking hosts / services with groups
    if view_spec["datasource"] in ["hosts", "services"]:
        if request.has_var("hostgroup") and not request.has_var("opthost_group"):
            request.set_var("opthost_group", request.get_str_input_mandatory("hostgroup"))
        if request.has_var("servicegroup") and not request.has_var("optservice_group"):
            request.set_var("optservice_group", request.get_str_input_mandatory("servicegroup"))

    # TODO: Another hack :( Just like the above one: When opening the view "ec_events_of_host",
    # which is of single context "host" using a host name of a unrelated event, the list of
    # events is always empty since the single context filter "host" is sending a "host_name = ..."
    # filter to livestatus which is not matching a "unrelated event". Instead the filter event_host
    # needs to be used.
    # But this may only be done for the unrelated events view. The "ec_events_of_monhost" view still
    # needs the filter. :-/
    # Another idea: We could change these views to non single context views, but then we would not
    # be able to show the buttons to other host related views, which is also bad. So better stick
    # with the current mode.
    if _is_ec_unrelated_host_view(view_spec):
        # Set the value for the event host filter
        if not request.has_var("event_host") and request.has_var("host"):
            request.set_var("event_host", request.get_str_input_mandatory("host"))


def process_view(view_renderer: ABCViewRenderer) -> None:
    """Rendering all kind of views"""
    if request.var("mode") == "availability":
        _process_availability_view(view_renderer)
    else:
        _process_regular_view(view_renderer)


def _process_regular_view(view_renderer: ABCViewRenderer) -> None:
    all_active_filters = _get_all_active_filters(view_renderer.view)
    with livestatus.intercept_queries() as queries:
        unfiltered_amount_of_rows, rows = _get_view_rows(
            view_renderer.view,
            all_active_filters,
            only_count=False,
        )

    if html.output_format != "html":
        _export_view(view_renderer.view, rows)
        return

    _add_rest_api_menu_entries(view_renderer, queries)
    _show_view(view_renderer, unfiltered_amount_of_rows, rows)


def _add_rest_api_menu_entries(view_renderer, queries: list[str]):  # type:ignore[no-untyped-def]
    from cmk.utils.livestatus_helpers.queries import Query

    from cmk.gui.plugins.openapi.utils import create_url

    entries: list[PageMenuEntry] = []
    for text_query in set(queries):
        if "\nStats:" in text_query:
            continue
        try:
            query = Query.from_string(text_query)
        except ValueError:
            continue
        try:
            url = create_url(omd_site(), query)
        except ValueError:
            continue
        table = query.table.__tablename__
        entries.append(
            PageMenuEntry(
                title=_("Query %s resource") % (table,),
                icon_name="filter",
                item=make_external_link(url),
            )
        )
    view_renderer.append_menu_topic(
        dropdown="export",
        topic=PageMenuTopic(
            title="REST API",
            entries=entries,
        ),
    )


def _process_availability_view(view_renderer: ABCViewRenderer) -> None:
    view = view_renderer.view
    all_active_filters = _get_all_active_filters(view)

    # Fork to availability view. We just need the filter headers, since we do not query the normal
    # hosts and service table, but "statehist". This is *not* true for BI availability, though (see
    # later)
    if "aggr" not in view.datasource.infos or request.var("timeline_aggr"):
        filterheaders = "".join(get_livestatus_filter_headers(view.context, all_active_filters))
        # all 'amount_*', 'duration_fetch_rows' and 'duration_filter_rows' will be set in:
        show_view_func = functools.partial(
            availability.show_availability_page,
            view=view,
            filterheaders=filterheaders,
        )

    else:
        _unfiltered_amount_of_rows, rows = _get_view_rows(
            view, all_active_filters, only_count=False
        )
        # 'amount_rows_after_limit' will be set in:
        show_view_func = functools.partial(
            availability.show_bi_availability,
            view=view,
            aggr_rows=rows,
        )

    with CPUTracker() as view_render_tracker:
        show_view_func()
    view.process_tracking.duration_view_render = view_render_tracker.duration


# TODO: Use livestatus Stats: instead of fetching rows?
def get_row_count(view: View) -> int:
    """Returns the number of rows shown by a view"""

    all_active_filters = _get_all_active_filters(view)
    # Check that all needed information for configured single contexts are available
    if view.missing_single_infos:
        raise MKUserError(
            None,
            _(
                "Missing context information: %s. You can either add this as a fixed "
                "setting, or call the with the missing HTTP variables."
            )
            % (", ".join(view.missing_single_infos)),
        )

    _unfiltered_amount_of_rows, rows = _get_view_rows(view, all_active_filters, only_count=True)
    return len(rows)


def _get_view_rows(
    view: View, all_active_filters: list[Filter], only_count: bool = False
) -> tuple[int, Rows]:
    with CPUTracker() as fetch_rows_tracker:
        # Fetch data. Some views show data only after pressing [Search]
        if (
            only_count
            or (not view.spec.get("mustsearch"))
            or request.var("filled_in") in ["filter", "actions", "confirm", "painteroptions"]
        ):
            rows, unfiltered_amount_of_rows = _fetch_rows_from_livestatus(view, all_active_filters)
        else:
            rows = []
            unfiltered_amount_of_rows = 0

        post_process_rows(view, all_active_filters, rows)

    # Sorting - use view sorters and URL supplied sorters
    _sort_data(rows, view.sorters)

    with CPUTracker() as filter_rows_tracker:
        # Apply non-Livestatus filters
        for filter_ in all_active_filters:
            try:
                rows = filter_.filter_table(view.context, rows)
            except MKMissingDataError as e:
                view.add_warning_message(str(e))

    view.process_tracking.amount_unfiltered_rows = unfiltered_amount_of_rows
    view.process_tracking.amount_filtered_rows = len(rows)
    view.process_tracking.duration_fetch_rows = fetch_rows_tracker.duration
    view.process_tracking.duration_filter_rows = filter_rows_tracker.duration

    return unfiltered_amount_of_rows, rows


def _fetch_rows_from_livestatus(view: View, all_active_filters: list[Filter]) -> tuple[Rows, int]:
    """Fetches the view rows from livestatus

    Besides gathering the information from livestatus it performs livestatus table joining
    (e.g. Adding service row info to host rows (For join painters))"""
    # We test for limit here and not inside view.row_limit, because view.row_limit is used
    # for rendering limits.
    row_data: Rows | tuple[Rows, int] = view.datasource.table.query(
        view.datasource,
        view.row_cells,
        _get_needed_regular_columns(
            all_active_filters,
            view,
        ),
        view.context,
        (
            "".join(get_livestatus_filter_headers(view.context, all_active_filters))
            + view.spec.get("add_headers", "")
        ),
        view.only_sites,
        None if view.datasource.ignore_limit else view.row_limit,
        all_active_filters,
    )

    if isinstance(row_data, tuple):
        rows, unfiltered_amount_of_rows = row_data
    else:
        rows = row_data
        unfiltered_amount_of_rows = len(row_data)

    # Now add join information, if there are join columns
    if view.join_cells:
        _do_table_join(view, all_active_filters, rows)

    return rows, unfiltered_amount_of_rows


def _show_view(view_renderer: ABCViewRenderer, unfiltered_amount_of_rows: int, rows: Rows) -> None:
    view = view_renderer.view

    # Load from hard painter options > view > hard coded default
    painter_options = PainterOptions.get_instance()
    num_columns = painter_options.get("num_columns", view.spec.get("num_columns", 1))
    browser_reload = painter_options.get("refresh", view.spec.get("browser_reload", None))

    force_checkboxes = view.spec.get("force_checkboxes", False)
    show_checkboxes = force_checkboxes or request.var("show_checkboxes", "0") == "1"

    show_filters = visuals.filters_of_visual(
        view.spec, view.datasource.infos, link_filters=view.datasource.link_filters
    )

    # Set browser reload
    if browser_reload and display_options.enabled(display_options.R):
        html.browser_reload = browser_reload

    if active_config.enable_sounds and active_config.sounds:
        for row in rows:
            save_state_for_playing_alarm_sounds(row)

    # Until now no single byte of HTML code has been output.
    # Now let's render the view
    with CPUTracker() as view_render_tracker:
        view_renderer.render(
            rows, show_checkboxes, num_columns, show_filters, unfiltered_amount_of_rows
        )
    view.process_tracking.duration_view_render = view_render_tracker.duration


def _get_all_active_filters(view: View) -> list[Filter]:
    # Always allow the users to specify all allowed filters using the URL
    use_filters = list(visuals.filters_allowed_for_infos(view.datasource.infos).values())

    # See process_view() for more information about this hack
    if _is_ec_unrelated_host_view(view.spec):
        # Remove the original host name filter
        use_filters = [f for f in use_filters if f.ident != "host"]

    use_filters = [f for f in use_filters if f.available()]

    for filt in use_filters:
        # TODO: Clean this up! E.g. make the Filter class implement a default method
        if hasattr(filt, "derived_columns"):
            filt.derived_columns(view.row_cells)  # type: ignore[attr-defined]

    return use_filters


def _export_view(view: View, rows: Rows) -> None:
    """Shows the views data in one of the supported machine readable formats"""
    layout = view.layout
    if html.output_format == "csv" and layout.has_individual_csv_export:
        layout.csv_export(rows, view.spec, view.group_cells, view.row_cells)
        return

    exporter = exporter_registry.get(html.output_format)
    if not exporter:
        raise MKUserError(
            "output_format", _("Output format '%s' not supported") % html.output_format
        )

    exporter.handler(view, rows)


def _is_ec_unrelated_host_view(view_spec: ViewSpec) -> bool:
    # The "name" is not set in view report elements
    return (
        view_spec["datasource"] in ["mkeventd_events", "mkeventd_history"]
        and "host" in view_spec["single_infos"]
        and view_spec.get("name") != "ec_events_of_monhost"
    )


def _get_needed_regular_columns(
    all_active_filters: Iterable[Filter],
    view: View,
) -> list[ColumnName]:
    """Compute the list of all columns we need to query via Livestatus

    Those are: (1) columns used by the sorters in use, (2) columns use by column- and group-painters
    in use and - note - (3) columns used to satisfy external references (filters) of views we link
    to. The last bit is the trickiest. Also compute this list of view options use by the painters
    """
    # BI availability needs aggr_tree
    # TODO: wtf? a full reset of the list? Move this far away to a special place!
    if request.var("mode") == "availability" and "aggr" in view.datasource.infos:
        return ["aggr_tree", "aggr_name", "aggr_group"]

    columns = columns_of_cells(view.group_cells + view.row_cells)

    # Columns needed for sorters
    # TODO: Move sorter parsing and logic to something like Cells()
    for entry in view.sorters:
        columns.update(entry.sorter.columns)

    # Add key columns, needed for executing commands
    columns.update(view.datasource.keys)

    # Add idkey columns, needed for identifying the row
    columns.update(view.datasource.id_keys)

    # Add columns requested by filters for post-livestatus filtering
    columns.update(
        chain.from_iterable(
            filter.columns_for_filter_table(view.context) for filter in all_active_filters
        )
    )

    # Remove (implicit) site column
    try:
        columns.remove("site")
    except KeyError:
        pass

    # In the moment the context buttons are shown, the link_from mechanism is used
    # to decide to which other views/dashboards the context buttons should link to.
    # This decision is partially made on attributes of the object currently shown.
    # E.g. on a "single host" page the host labels are needed for the decision.
    # This is currently realized explicitly until we need a more flexible mechanism.
    if display_options.enabled(display_options.B) and "host" in view.datasource.infos:
        columns.add("host_labels")

    return list(columns)


def _get_needed_join_columns(
    join_cells: list[JoinCell], sorters: list[SorterEntry]
) -> list[ColumnName]:
    join_columns = columns_of_cells(join_cells)

    # Columns needed for sorters
    # TODO: Move sorter parsing and logic to something like Cells()
    for entry in sorters:
        join_columns.update(entry.sorter.columns)

    # Remove (implicit) site column
    try:
        join_columns.remove("site")
    except KeyError:
        pass

    return list(join_columns)


def columns_of_cells(cells: Sequence[Cell]) -> set[ColumnName]:
    columns: set[ColumnName] = set()
    permitted_views = get_permitted_views()
    for cell in cells:
        columns.update(cell.needed_columns(permitted_views))
    return columns


def _do_table_join(view: View, all_active_filters: list[Filter], master_rows: Rows) -> None:
    if not (isinstance(join := view.datasource.join, tuple) and len(join) == 2):
        raise ValueError()

    join_table, join_master_column = join
    slave_ds = data_source_registry[join_table]()

    if slave_ds.join_key is None:
        raise ValueError()

    row_data = slave_ds.table.query(
        view.datasource,
        view.row_cells,
        columns=list(
            set(
                [join_master_column, slave_ds.join_key]
                + _get_needed_join_columns(view.join_cells, view.sorters)
            )
        ),
        context=view.context,
        headers="{}{}\n".format(
            "".join(get_livestatus_filter_headers(view.context, all_active_filters)),
            "\n".join(_make_join_filters(view.join_cells, slave_ds.join_key)),
        ),
        only_sites=view.only_sites,
        limit=None,
        all_active_filters=[],
    )

    if isinstance(row_data, tuple):
        rows, _unfiltered_amount_of_rows = row_data
    else:
        rows = row_data

    per_master_entry: dict[tuple[SiteId, str], dict[str, Row]] = {}
    for row in rows:
        current_entry = per_master_entry.setdefault(_make_master_key(row, join_master_column), {})
        current_entry[row[slave_ds.join_key]] = row

    # Add this information into master table in artificial column "JOIN"
    for row in master_rows:
        row["JOIN"] = per_master_entry.get(_make_master_key(row, join_master_column), {})


def _make_join_filters(join_cells: list[JoinCell], join_key: str) -> list[str]:
    join_filters = [join_cell.livestatus_filter(join_key) for join_cell in join_cells]
    join_filters.append("Or: %d" % len(join_filters))
    return join_filters


def _make_master_key(row: Row, join_master_column: str) -> tuple[SiteId, str]:
    return (SiteId(row["site"]), row[join_master_column])


def save_state_for_playing_alarm_sounds(row: "Row") -> None:
    if not active_config.enable_sounds or not active_config.sounds:
        return

    # TODO: Move this to a generic place. What about -1?
    host_state_map = {0: "up", 1: "down", 2: "unreachable"}
    service_state_map = {0: "up", 1: "warning", 2: "critical", 3: "unknown"}

    for state_map, state in [
        (host_state_map, row.get("host_hard_state", row.get("host_state"))),
        (service_state_map, row.get("service_last_hard_state", row.get("service_state"))),
    ]:
        if state is None:
            continue

        try:
            state_name = state_map[int(state)]
        except KeyError:
            continue

        g.setdefault("alarm_sound_states", set()).add(state_name)


def _parse_url_sorters(
    config_sorters: Sequence[SorterSpec], cells: Sequence[Cell], sort: str | None
) -> list[SorterSpec]:
    sorters: list[SorterSpec] = []
    sorter: SorterName | tuple[SorterName, PainterParameters]
    if not sort:
        return sorters
    for s in sort.split(","):
        if "~" in s:
            sorter, join_index = s.split("~", 1)
        else:
            sorter, join_index = s, None

        negate = False
        if sorter.startswith("-"):
            negate = True
            sorter = sorter[1:]

        if ":" in sorter:
            sorter, ident = sorter.split(":", 1)
            parameters = _sorter_parameters_by_ident(config_sorters, cells, sorter, ident)
            if parameters is None:
                continue  # Skip sorters with unresolvable parameters
            sorter = (sorter, parameters)

        sorters.append(SorterSpec(sorter, negate, join_index))
    return sorters


def _sorter_parameters_by_ident(
    sorters: Sequence[SorterSpec], cells: Sequence[Cell], sorter_name: str, ident: str
) -> PainterParameters | None:
    """Resolve sorter reference to configured parameters

    We can not transport the sorter parameters through the URL of a view. So only a reference in the
    form "name:ident" is used. We now need to be resolv this reference by looking up the reference
    either in the sorters or the configured painters.
    """
    for sorter_spec in sorters:
        sorter = sorter_spec.sorter
        if (
            isinstance(sorter, tuple)
            and sorter[0] == sorter_name
            # Consolidate "uuid" to "ident" for a cleaner handling here
            and sorter[1].get("ident", sorter[1].get("uuid")) == ident
        ):
            return sorter[1]

    for cell in cells:
        if (params := cell.painter_parameters()) is None:
            params = {}

        if cell.painter_name() == sorter_name and params.get("ident", params.get("uuid")):
            return params

    return None


def get_user_sorters(sorters: Sequence[SorterSpec], cells: Sequence[Cell]) -> list[SorterSpec]:
    """Returns a list of optionally set sort parameters from HTTP request"""
    return _parse_url_sorters(sorters, cells, request.var("sort"))


def get_want_checkboxes() -> bool:
    """Whether or not the user requested checkboxes to be shown"""
    return request.get_integer_input_mandatory("show_checkboxes", 0) == 1


def get_limit() -> int | None:
    """How many data rows may the user query?"""
    limitvar = request.var("limit", "soft")
    if limitvar == "hard" and user.may("general.ignore_soft_limit"):
        return active_config.hard_query_limit
    if limitvar == "none" and user.may("general.ignore_hard_limit"):
        return None
    return active_config.soft_query_limit


def _link_to_folder_by_path(path: str) -> str:
    """Return an URL to a certain WATO folder when we just know its path"""
    return makeuri_contextless(
        request,
        [("mode", "folder"), ("folder", path)],
        filename="wato.py",
    )


def _sort_data(data: "Rows", sorters: list[SorterEntry]) -> None:
    """Sort data according to list of sorters."""
    if not sorters:
        return

    # Handle case where join columns are not present for all rows
    def safe_compare(
        compfunc: Callable[[Row, Row, Mapping[str, Any] | None], int],
        row1: Row,
        row2: Row,
        parameters: Mapping[str, Any] | None,
    ) -> int:
        if row1 is None and row2 is None:
            return 0
        if row1 is None:
            return -1
        if row2 is None:
            return 1
        return compfunc(
            row1,
            row2,
            parameters,
        )

    def multisort(e1: Row, e2: Row) -> int:
        for entry in sorters:
            neg = -1 if entry.negate else 1

            if entry.join_key:  # Sorter for join column, use JOIN info
                c = neg * safe_compare(
                    entry.sorter.cmp,
                    e1["JOIN"].get(entry.join_key),
                    e2["JOIN"].get(entry.join_key),
                    entry.parameters,
                )
            else:
                c = neg * entry.sorter.cmp(e1, e2, entry.parameters)

            if c != 0:
                return c
        return 0  # equal

    data.sort(key=functools.cmp_to_key(multisort))
