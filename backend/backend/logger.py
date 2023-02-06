"""
Defines the logging format for the console logger
"""
import logging
from django.utils.termcolors import colorize


class ConsoleFormatter(logging.Formatter):
    """
    Class to define a formatter to be used to format the console logs
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def format(self, record):
        default_time_format = "%I:%M:%S %p, %d/%b/%Y"

        # Retrieve the status and formatted message from the record
        msg = f"[{record.levelname}] " + record.getMessage()
        status = record.levelname

        # Assign an appropriate color to each level of status
        if status == "WARNING":
            msg = colorize(msg, fg="magenta", opts=("bold",))
        elif status == "ERROR":
            msg = colorize(msg, fg="yellow", opts=("bold",))
        elif status == "CRITICAL":
            msg = colorize(msg, fg="red", opts=("bold",))
        elif status == "INFO":
            msg = colorize(msg, fg="blue")

        # Write new console values into the record
        record.server_time = self.formatTime(record, default_time_format)
        record.console_msg = msg

        # Return the new formatted record
        return super().format(record)
