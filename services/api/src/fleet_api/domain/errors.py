class DomainError(ValueError):
    """Base class for expected domain invariant failures."""


class NotFoundError(DomainError):
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
