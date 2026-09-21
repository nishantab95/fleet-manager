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
