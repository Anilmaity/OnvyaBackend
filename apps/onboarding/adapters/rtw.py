from django.utils import timezone


class RtwAdapter:
    def check(self, driver):
        return {"status": "passed", "verified_at": timezone.now().isoformat()}
