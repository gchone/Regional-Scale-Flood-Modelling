import arcpy

class Messages:
    def __init__(self, manager):
        self.manager = manager

    def add_message(self, message):
        """Add a message to the ArcGIS tool messages."""
        self.manager.addMessage(message)

    def add_warning(self, message):
        """Add a warning message to the ArcGIS tool messages."""
        self.manager.addWarningMessage(message)

    def add_error(self, message):
        """Add an error message to the ArcGIS tool messages."""
        self.manager.addErrorMessage(message)
        raise Exception("Fatal error, stopping process.")
