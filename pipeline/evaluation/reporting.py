"""Final evaluation report renderer (Step 8, lightweight)."""

from pipeline.evaluation.lead_time_report import LeadTimeSummary
from pipeline.evaluation.retrievability_report import CountryRetrievabilitySummary


def _fmt(value: float | None, suffix: str = "") -> str:
    return "N/A" if value is None else f"{value:.1f}{suffix}"


def render_final_report(
    lead_time_summary: LeadTimeSummary,
    retrievability_summaries: list[CountryRetrievabilitySummary],
    limitations: list[str],
) -> str:
    s = lead_time_summary
    win_rate_pct = None if s.content_win_rate is None else s.content_win_rate * 100

    lines = [
        "# Final Evaluation",
        "",
        "## Lead-time distribution",
        "",
        f"- Country-seasons evaluated: {s.n_total} ({s.n_excluded} excluded, insufficient data)",
        (
            f"- Content signal detected in {s.n_content_detected} country-seasons; "
            f"frequency baseline in {s.n_frequency_detected}"
        ),
        (
            f"- Content lead time (days, negative = early): mean {_fmt(s.content_lead_mean_days)}, "
            f"median {_fmt(s.content_lead_median_days)}, stdev {_fmt(s.content_lead_stdev_days)}"
        ),
        (
            f"- Frequency baseline lead time (days): mean {_fmt(s.frequency_lead_mean_days)}, "
            f"median {_fmt(s.frequency_lead_median_days)}, stdev {_fmt(s.frequency_lead_stdev_days)}"
        ),
        f"- Content win rate vs frequency baseline: {_fmt(win_rate_pct, '%')}",
        "",
        "## Retrievability / content-depth (full scale vs spike's 88%/88%)",
        "",
    ]

    if not retrievability_summaries:
        lines.append("(no retrievability data available)")
    else:
        lines.append("| Country | Articles | % Retrievable | % Content-rich |")
        lines.append("|---|---|---|---|")
        for r in retrievability_summaries:
            lines.append(
                f"| {r.country_iso3} | {r.n_articles} | {r.pct_retrievable:.1f} | "
                f"{r.pct_content_rich:.1f} |"
            )

    lines += ["", "## Limitations", ""]
    if not limitations:
        lines.append("(none recorded)")
    else:
        lines += [f"- {item}" for item in limitations]

    return "\n".join(lines)
