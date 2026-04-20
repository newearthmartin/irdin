import logging


class ShortNameFormatter(logging.Formatter):
    """Formatter that uses only the last segment of the logger name."""

    def format(self, record):
        record.name = record.name.rsplit(".", 1)[-1]
        return super().format(record)
