class AgencyContextMissing(Exception):
    """Raised when a scoped query runs with no agency context in strict mode."""


class CrossAgencyWriteRejected(Exception):
    """Raised when a service tries to write a row whose agency_id != current agency."""
