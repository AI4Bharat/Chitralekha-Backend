import re

# Regular expression pattern to match the format "00:00:00.000"
pattern = r"^\d{2}:\d{2}:\d{2}\.$"


def format_timestamp(timestamp_string):
    # Check if the timestamp matches the format
    if re.match(pattern, timestamp_string):
        corrected_timestamp = timestamp_string + "000"  # Add "000" for milliseconds
    else:
        # Split the timestamp into components
        components = timestamp_string.split(".")

        # Ensure the milliseconds component has three digits
        milliseconds = components[1].ljust(3, "0")

        # Format the corrected timestamp
        corrected_timestamp = f"{components[0]}.{milliseconds}"

    return corrected_timestamp
