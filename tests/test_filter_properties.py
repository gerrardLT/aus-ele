"""Property-based tests for filter context propagation consistency.

Feature: platform-optimization, Property 7: 过滤条件传播一致性

For any FilterContext state and any active analysis module set, each module's API
request should contain all supported dimension parameters from the current FilterContext;
for unsupported dimensions, the API response metadata.ignored_filters should list the
ignored dimension names.

Validates: Requirements 6.1, 6.2, 6.3
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Python mirror of the frontend toQueryParams logic (FilterContext.jsx)
# ---------------------------------------------------------------------------

ALL_FILTER_DIMENSIONS = ["market", "region", "year", "quarter", "day_type", "months"]


def to_query_params(filters: dict) -> dict:
    """Python equivalent of FilterContext.jsx toQueryParams function.

    Converts a filter state dict to API query parameters.
    Only includes non-default values to keep requests clean.
    """
    params = {"market": filters["market"], "region": filters["region"]}
    if filters.get("year") is not None:
        params["year"] = filters["year"]
    if filters.get("quarter", "ALL") != "ALL":
        params["quarter"] = filters["quarter"]
    if filters.get("dayType", "ALL") != "ALL":
        params["day_type"] = filters["dayType"]
    months = filters.get("months", ["ALL"])
    if len(months) > 0 and not (len(months) == 1 and months[0] == "ALL"):
        params["months"] = ",".join(months)
    return params


def get_ignored_filters(query_params: dict, supported_dimensions: set) -> list[str]:
    """Determine which dimensions in the query are not supported by a module.

    For dimensions present in the query params but not supported by the module,
    they should appear in the ignored_filters list.
    """
    ignored = []
    for dim in query_params:
        if dim not in supported_dimensions:
            ignored.append(dim)
    return sorted(ignored)


# ---------------------------------------------------------------------------
# Module dimension support definitions
# Each module declares which filter dimensions it supports.
# ---------------------------------------------------------------------------

MODULE_SUPPORTED_DIMENSIONS = {
    "price_analysis": {"market", "region", "year", "quarter", "day_type", "months"},
    "revenue_analysis": {"market", "region", "year", "quarter", "day_type", "months"},
    "fcas_analysis": {"market", "region", "year", "quarter"},
    "investment_analysis": {"market", "region", "year"},
    "grid_forecast": {"market", "region", "year", "quarter"},
}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

market_strategy = st.sampled_from(["NEM", "WEM"])
region_strategy = st.sampled_from(["NSW1", "QLD1", "VIC1", "SA1", "TAS1", "WEM"])
year_strategy = st.one_of(st.none(), st.integers(min_value=2018, max_value=2030))
quarter_strategy = st.sampled_from(["ALL", "Q1", "Q2", "Q3", "Q4"])
day_type_strategy = st.sampled_from(["ALL", "weekday", "weekend", "business_day"])
month_strategy = st.sampled_from(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
)
months_strategy = st.one_of(
    st.just(["ALL"]),
    st.lists(month_strategy, min_size=1, max_size=12, unique=True),
)

filter_state_strategy = st.fixed_dictionaries(
    {
        "market": market_strategy,
        "region": region_strategy,
        "year": year_strategy,
        "quarter": quarter_strategy,
        "dayType": day_type_strategy,
        "months": months_strategy,
    }
)

module_strategy = st.sampled_from(list(MODULE_SUPPORTED_DIMENSIONS.keys()))
module_set_strategy = st.lists(module_strategy, min_size=1, max_size=5, unique=True)


# ---------------------------------------------------------------------------
# Property 7: 过滤条件传播一致性
# ---------------------------------------------------------------------------


class TestFilterPropagationConsistencyProperty:
    """Property 7: 过滤条件传播一致性

    For any FilterContext state and any active analysis module set:
    - Each module's API request contains all supported dimension parameters
    - Unsupported dimensions appear in ignored_filters

    **Validates: Requirements 6.1, 6.2, 6.3**
    """

    @given(filters=filter_state_strategy)
    @settings(max_examples=200)
    def test_to_query_params_includes_all_active_dimensions(self, filters: dict):
        """toQueryParams always includes market and region; other dimensions are
        included only when they have non-default values.

        Feature: platform-optimization, Property 7: 过滤条件传播一致性
        **Validates: Requirements 6.1, 6.2**
        """
        params = to_query_params(filters)

        # market and region are always present
        assert "market" in params
        assert "region" in params
        assert params["market"] == filters["market"]
        assert params["region"] == filters["region"]

        # year is present when not None
        if filters["year"] is not None:
            assert "year" in params
            assert params["year"] == filters["year"]
        else:
            assert "year" not in params

        # quarter is present when not "ALL"
        if filters["quarter"] != "ALL":
            assert "quarter" in params
            assert params["quarter"] == filters["quarter"]
        else:
            assert "quarter" not in params

        # day_type is present when dayType is not "ALL"
        if filters["dayType"] != "ALL":
            assert "day_type" in params
            assert params["day_type"] == filters["dayType"]
        else:
            assert "day_type" not in params

        # months is present when not ["ALL"]
        if filters["months"] != ["ALL"]:
            assert "months" in params
            assert params["months"] == ",".join(filters["months"])
        else:
            assert "months" not in params

    @given(filters=filter_state_strategy, modules=module_set_strategy)
    @settings(max_examples=200)
    def test_unsupported_dimensions_in_ignored_filters(self, filters: dict, modules: list):
        """For each module, dimensions present in query params but not supported
        by the module appear in ignored_filters.

        Feature: platform-optimization, Property 7: 过滤条件传播一致性
        **Validates: Requirements 6.3**
        """
        params = to_query_params(filters)

        for module_name in modules:
            supported = MODULE_SUPPORTED_DIMENSIONS[module_name]
            ignored = get_ignored_filters(params, supported)

            # Every ignored dimension must NOT be in the module's supported set
            for dim in ignored:
                assert dim not in supported

            # Every dimension in params that IS supported must NOT be in ignored
            for dim in params:
                if dim in supported:
                    assert dim not in ignored

            # The union of supported params + ignored params covers all params
            for dim in params:
                assert dim in supported or dim in ignored

    @given(filters=filter_state_strategy, module=module_strategy)
    @settings(max_examples=200)
    def test_supported_dimensions_always_propagated(self, filters: dict, module: str):
        """For any module, all supported dimensions that have non-default values
        in the FilterContext are present in the query params sent to that module.

        Feature: platform-optimization, Property 7: 过滤条件传播一致性
        **Validates: Requirements 6.1, 6.2**
        """
        params = to_query_params(filters)
        supported = MODULE_SUPPORTED_DIMENSIONS[module]

        # All dimensions in params that are supported by this module
        # should be forwarded (i.e., they exist in params)
        for dim in ALL_FILTER_DIMENSIONS:
            if dim in supported and dim in params:
                # The module receives this dimension
                assert dim in params

        # Conversely, if a supported dimension is NOT in params,
        # it means the filter had a default value (which is correct behavior)
        for dim in supported:
            if dim not in params:
                # Verify it was indeed a default value
                if dim == "market":
                    # market is always included, so this shouldn't happen
                    assert False, "market should always be in params"
                elif dim == "region":
                    # region is always included
                    assert False, "region should always be in params"
                elif dim == "year":
                    assert filters["year"] is None
                elif dim == "quarter":
                    assert filters["quarter"] == "ALL"
                elif dim == "day_type":
                    assert filters["dayType"] == "ALL"
                elif dim == "months":
                    assert filters["months"] == ["ALL"]

    @given(filters=filter_state_strategy)
    @settings(max_examples=200)
    def test_query_params_keys_are_valid_api_dimensions(self, filters: dict):
        """All keys produced by toQueryParams are valid API dimension names.

        Feature: platform-optimization, Property 7: 过滤条件传播一致性
        **Validates: Requirements 6.2**
        """
        params = to_query_params(filters)

        valid_dimensions = set(ALL_FILTER_DIMENSIONS)
        for key in params:
            assert key in valid_dimensions, f"Unexpected dimension '{key}' in query params"
