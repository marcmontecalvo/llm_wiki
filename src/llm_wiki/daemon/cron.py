"""Cron expression parsing and scheduling utilities."""

from datetime import UTC, datetime, timedelta


class CronParser:
    """Parse and validate cron expressions.

    Supports standard cron format: minute hour day month weekday
    Examples:
        "0 2 * * *" - Daily at 2 AM
        "*/30 * * * *" - Every 30 minutes
        "0 */6 * * *" - Every 6 hours
        "0 9 * * 1-5" - Weekdays at 9 AM
    """

    # Field names and their valid ranges
    FIELD_RANGES = {
        "minute": (0, 59),
        "hour": (0, 23),
        "day": (1, 31),
        "month": (1, 12),
        "weekday": (0, 6),  # 0 = Sunday, 6 = Saturday
    }

    MONTH_NAMES = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    WEEKDAY_NAMES = {
        "sun": 0,
        "mon": 1,
        "tue": 2,
        "wed": 3,
        "thu": 4,
        "fri": 5,
        "sat": 6,
    }

    def __init__(self, expression: str):
        """Initialize cron parser.

        Args:
            expression: Cron expression (minute hour day month weekday)

        Raises:
            ValueError: If expression is invalid
        """
        self.expression = expression.strip()
        self.fields = self._parse_expression()

    def _parse_expression(self) -> dict[str, list[int]]:
        """Parse cron expression into field values.

        Returns:
            Dictionary mapping field names to lists of valid values

        Raises:
            ValueError: If expression is invalid
        """
        parts = self.expression.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: expected 5 fields, got {len(parts)}")

        field_names = ["minute", "hour", "day", "month", "weekday"]
        result = {}

        for name, part in zip(field_names, parts, strict=False):
            try:
                result[name] = self._parse_field(name, part)
            except ValueError as e:
                raise ValueError(f"Invalid {name} field '{part}': {e}") from e

        return result

    def _parse_field(self, field_name: str, field_value: str) -> list[int]:
        """Parse a single cron field.

        Args:
            field_name: Name of field (minute, hour, etc.)
            field_value: Field value (*, number, range, list, step)

        Returns:
            List of valid values for this field

        Raises:
            ValueError: If field value is invalid
        """
        min_val, max_val = self.FIELD_RANGES[field_name]

        # Handle wildcard
        if field_value == "*":
            return list(range(min_val, max_val + 1))

        # Handle step values (*/5, 0-20/5)
        if "/" in field_value:
            range_part, step_str = field_value.rsplit("/", 1)
            try:
                step = int(step_str)
                if step <= 0:
                    raise ValueError("step must be positive")
            except ValueError as e:
                raise ValueError(f"invalid step value: {step_str}") from e

            if range_part == "*":
                return list(range(min_val, max_val + 1, step))
            else:
                # Range with step (e.g., 0-20/5)
                range_values = self._parse_range(field_name, range_part)
                if not range_values:
                    return []
                return [v for v in range_values if (v - min_val) % step == 0]

        # Handle ranges (0-10, mon-fri)
        if "-" in field_value:
            return self._parse_range(field_name, field_value)

        # Handle lists (1,3,5,10)
        if "," in field_value:
            values = []
            for part in field_value.split(","):
                part = part.strip()
                if "-" in part:
                    values.extend(self._parse_range(field_name, part))
                else:
                    values.append(self._parse_number(field_name, part))
            return sorted(set(values))

        # Single value
        return [self._parse_number(field_name, field_value)]

    def _parse_range(self, field_name: str, range_str: str) -> list[int]:
        """Parse a range expression.

        Args:
            field_name: Field name
            range_str: Range string (e.g., "0-10" or "mon-fri")

        Returns:
            List of values in range

        Raises:
            ValueError: If range is invalid
        """
        parts = range_str.split("-")
        if len(parts) != 2:
            raise ValueError(f"invalid range: {range_str}")

        start = self._parse_number(field_name, parts[0])
        end = self._parse_number(field_name, parts[1])

        if start > end:
            raise ValueError(f"range start ({start}) > end ({end})")

        return list(range(start, end + 1))

    def _parse_number(self, field_name: str, value: str) -> int:
        """Parse a number, handling named values for months/weekdays.

        Args:
            field_name: Field name
            value: Value to parse

        Returns:
            Integer value

        Raises:
            ValueError: If value is invalid
        """
        value = value.lower().strip()

        # Handle named values for months
        if field_name == "month" and value in self.MONTH_NAMES:
            return self.MONTH_NAMES[value]

        # Handle named values for weekdays
        if field_name == "weekday" and value in self.WEEKDAY_NAMES:
            return self.WEEKDAY_NAMES[value]

        # Parse as integer
        try:
            num = int(value)
        except ValueError as e:
            raise ValueError(f"cannot parse '{value}' as number") from e

        # Validate range
        min_val, max_val = self.FIELD_RANGES[field_name]
        if num < min_val or num > max_val:
            raise ValueError(f"value {num} out of range [{min_val}, {max_val}]")

        return num

    def get_next_run_time(self, reference_time: datetime | None = None) -> datetime:
        """Calculate next run time based on this cron expression.

        Args:
            reference_time: Reference time (default: now UTC)

        Returns:
            Next scheduled run time

        Note:
            This is a simplified calculation that doesn't handle all edge cases
            (e.g., Feb 30). For production use, consider using the croniter library.
        """
        if reference_time is None:
            reference_time = datetime.now(UTC)

        # Start from next minute
        current = reference_time.replace(second=0, microsecond=0) + timedelta(minutes=1)

        # Search for next matching time (max 4 years)
        end_search = current + timedelta(days=365 * 4)

        while current <= end_search:
            if self._matches(current):
                return current
            current += timedelta(minutes=1)

        raise RuntimeError(f"Could not find next run time for: {self.expression}")

    def _matches(self, dt: datetime) -> bool:
        """Check if datetime matches this cron expression.

        Args:
            dt: Datetime to check

        Returns:
            True if datetime matches
        """
        return (
            dt.minute in self.fields["minute"]
            and dt.hour in self.fields["hour"]
            and dt.day in self.fields["day"]
            and dt.month in self.fields["month"]
            and dt.weekday() in self._adjust_weekday(self.fields["weekday"])
        )

    def _adjust_weekday(self, weekday_values: list[int]) -> list[int]:
        """Adjust weekday values from cron format (0=Sun) to Python format (0=Mon).

        Args:
            weekday_values: Weekday values in cron format

        Returns:
            Weekday values in Python format
        """
        # Cron: 0=Sunday, 6=Saturday
        # Python: 0=Monday, 6=Sunday
        result = []
        for val in weekday_values:
            if val == 0:  # Sunday in cron
                result.append(6)  # Sunday in Python
            else:
                result.append(val - 1)  # Shift by 1 for Mon-Sat
        return result

    def is_valid(self) -> bool:
        """Check if this is a valid cron expression.

        Returns:
            True if valid
        """
        try:
            self._parse_expression()
            return True
        except ValueError:
            return False

    def __str__(self) -> str:
        """String representation."""
        return f"CronParser('{self.expression}')"

    def __repr__(self) -> str:
        """Detailed representation."""
        return f"CronParser(expression='{self.expression}', fields={self.fields})"


def validate_cron_expression(expression: str) -> tuple[bool, str | None]:
    """Validate a cron expression.

    Args:
        expression: Cron expression to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        CronParser(expression)
        return True, None
    except ValueError as e:
        return False, str(e)
