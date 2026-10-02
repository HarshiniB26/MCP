class EquipmentError(Exception):
    """Base error for the equipment request system."""


class ConfigurationError(EquipmentError):
    """A required setting or input is missing."""


class DirectoryError(EquipmentError):
    """Employee or policy data could not be read."""


class ModelError(EquipmentError):
    """The model endpoint did not return a usable response."""
