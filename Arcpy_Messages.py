import arcpy

class Messages:
    """A simple message manager to handle messages in ArcGIS tools."""

    def add_message(self, message):
        arcpy.AddMessage(message)

    def add_warning(self, message):
        arcpy.AddWarning(message)

    def add_error(self, message):
        arcpy.AddError(message)
        raise Exception("Fatal error, stopping process.")