class UnknownTrack(ValueError):
    pass


class UnknownMetric(ValueError):
    pass


class FeatureLocked(Exception):
    def __init__(self, track: str) -> None:
        super().__init__(track)
        self.track = track
