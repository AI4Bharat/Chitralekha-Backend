from uuid import UUID

def validate_uuid4(val):
    try:
        UUID(str(val))
        return True
    except ValueError:
        return False
