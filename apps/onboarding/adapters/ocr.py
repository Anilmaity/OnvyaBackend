class OcrAdapter:
    def extract(self, file_path, kind):
        return {
            "kind": kind,
            "first_name": "Test",
            "last_name": "Driver",
            "licence_number": "TESTL123456",
            "expiry": "2030-01-01",
        }
