from __future__ import annotations


def join_readable(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def make_monitoring_headline(alert_count: int, system_name: str) -> str:
    if alert_count == 0:
        return f"{system_name} is currently treating groups consistently"
    if alert_count == 1:
        return f"{system_name} shows one fairness warning that needs attention"
    return f"{system_name} shows {alert_count} fairness warnings that need attention"
