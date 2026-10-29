"""Validate source-index references in saved geometry method outputs."""


def check(indices: object, point_count: int) -> dict:
    """Record whether every reported source index refers to an input point."""
    is_list = isinstance(indices, list)
    values = indices if is_list else []
    invalid_positions = [position for position, index in enumerate(values)
                         if type(index) is not int or index < 0 or index >= point_count]
    return {
        "schema": "csl.exp06-source-index-check/1",
        "status": "verified" if is_list and not invalid_positions else "incorrect",
        "point_count": point_count,
        "reported_count": len(values),
        "invalid_positions": invalid_positions,
    }
