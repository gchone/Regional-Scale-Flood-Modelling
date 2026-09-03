from qgis.core import QgsProcessingException

class Messages:

    def __init__(self, feedback):
        self.feedback = feedback

    def add_message(self, message):
        """Add a message to the QGIS tool messages."""
        self.feedback.pushInfo(message)


    def add_warning(self, message):
        """Add a warning message to the QGIS tool messages."""
        self.feedback.pushWarning(message)

    def add_error(self, message):
        """Add an error message to the QGIS tool messages."""
        self.feedback.reportError(message)
        raise QgsProcessingException("Fatal error, stopping process.")