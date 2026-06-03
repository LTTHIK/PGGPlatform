# Copyright (c) 2024 Microsoft Corporation.
# Licensed under the MIT License

"""All the steps to transform final entities."""

import logging

import pandas as pd

from graphrag.data_model.schemas import COMMUNITY_ID, COMMUNITY_REPORTS_FINAL_COLUMNS
from graphrag.index.utils.hashing import gen_sha512_hash

logger = logging.getLogger(__name__)


def finalize_community_reports(
    reports: pd.DataFrame,
    communities: pd.DataFrame,
) -> pd.DataFrame:
    """All the steps to transform final community reports."""
    if reports.empty or COMMUNITY_ID not in reports.columns:
        # Empty happens when every LLM call in summarize_communities returns None
        # (e.g. model does not satisfy structured JSON output).
        logger.warning(
            "No community reports to finalize (empty DataFrame or missing 'community' column). "
            "This usually means all community report LLM calls failed. "
            "Returning an empty community_reports table; global search will lack community summaries. "
            "Check logs for extraction errors and use a model with reliable JSON/schema output."
        )
        return pd.DataFrame(columns=COMMUNITY_REPORTS_FINAL_COLUMNS)

    # Merge with communities to add shared fields
    community_reports = reports.merge(
        communities.loc[:, ["community", "parent", "children", "size", "period"]],
        on="community",
        how="left",
        copy=False,
    )

    community_reports["community"] = community_reports["community"].astype(int)
    community_reports["human_readable_id"] = community_reports["community"]
    community_reports["id"] = community_reports.apply(
        lambda row: gen_sha512_hash(row, ["full_content"]), axis=1
    )

    return community_reports.loc[
        :,
        COMMUNITY_REPORTS_FINAL_COLUMNS,
    ]
