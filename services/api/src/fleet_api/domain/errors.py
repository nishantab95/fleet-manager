from decimal import Decimal


class DomainError(ValueError):
    """Base class for expected domain invariant failures."""


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class TenantConsistencyError(DomainError):
    pass


class RoleViolationError(DomainError):
    pass


class AssignmentConflictError(DomainError):
    pass


class AssignmentNotEffectiveError(DomainError):
    pass


class DuplicateAccessError(DomainError):
    pass


class EventTypeMismatchError(DomainError):
    pass


class PhoneNormalizationError(DomainError):
    pass


class AuthenticationError(DomainError):
    pass


class InvalidOtpError(AuthenticationError):
    pass


class MembershipSelectionError(AuthenticationError):
    pass


class InvalidTokenError(AuthenticationError):
    pass


class RefreshTokenReuseError(AuthenticationError):
    pass


class AuthConfigurationError(DomainError):
    pass


class OtpProviderUnavailableError(DomainError):
    pass


class OtpRateLimitError(AuthenticationError):
    pass


class EvidenceValidationError(DomainError):
    pass


class ObjectStorageUnavailableError(DomainError):
    pass


class ClosureBlockedError(DomainError):
    def __init__(self, message: str, blockers: list[dict[str, str]]) -> None:
        super().__init__(message)
        self.blockers = blockers


class DutyNotStartedError(DomainError):
    pass


class DutyAlreadyStartedError(DomainError):
    pass


class DutySessionClosedError(DomainError):
    pass


class DutyAssignmentMismatchError(DomainError):
    pass


class DutyEventOutsideSessionError(DomainError):
    pass


class DutyKmValidationError(DomainError):
    pass


class DutyOdometerContinuityError(DomainError):
    def __init__(self, message: str, *, previous_end_km: Decimal) -> None:
        super().__init__(message)
        self.previous_end_km = previous_end_km


class DutyOdometerOutOfRangeError(DomainError):
    pass
