from django.utils import timezone


class DvlaAdapter:
    def check(self, driver):
        return {
            "status": "passed",
            "licence_valid": True,
            "points": 0,
            "checked_at": timezone.now().isoformat(),
        }
