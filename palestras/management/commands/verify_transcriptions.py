import re
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from palestras.models import AudioTrack

TIMESTAMP_RE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\]\s*(.*)")

# Thresholds
TRUNCATION_RATIO = 0.80       # last timestamp < 80% of audio duration → truncated
DRIFT_MARGIN_SECS = 120       # last timestamp > audio_duration + 2min → drift
MIN_WORDS_PER_MINUTE = 15     # below this → suspiciously sparse
GAP_THRESHOLD_SECS = 300      # gap > 5min between consecutive segments → flagged


def _parse_timecoded(text):
    """Return list of (start_secs, text) from timecoded transcription."""
    segments = []
    for line in text.splitlines():
        m = TIMESTAMP_RE.match(line)
        if m:
            h, mi, s, txt = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            segments.append((h * 3600 + mi * 60 + s, txt))
    return segments


def _audio_duration(path):
    """Return audio duration in seconds via ffprobe, or None on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def _fmt(secs):
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class Command(BaseCommand):
    help = "Run sanity checks on transcribed AudioTrack records"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=0, help="Max tracks to check (0=all)"
        )
        parser.add_argument(
            "--method", type=str, default="", help="Filter by transcription_method substring"
        )
        parser.add_argument(
            "--no-ffprobe", action="store_true",
            help="Skip audio duration checks (faster, no ffprobe needed)"
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        method_filter = options["method"]
        skip_ffprobe = options["no_ffprobe"]

        qs = AudioTrack.objects.filter(transcribed_on__isnull=False).select_related("palestra")
        if method_filter:
            qs = qs.filter(transcription_method__icontains=method_filter)
        if limit:
            qs = qs[:limit]

        tracks = list(qs)
        self.stdout.write(f"Checking {len(tracks)} transcribed tracks...\n")

        issues = {
            "empty_transcription": [],
            "no_timecoded": [],
            "audio_missing": [],
            "truncated": [],
            "duration_drift": [],
            "non_monotonic": [],
            "low_word_density": [],
            "large_gap": [],
        }

        ok = 0

        for i, track in enumerate(tracks, 1):
            track_issues = []

            # 1. Empty transcription
            if not track.transcription.strip():
                track_issues.append("empty_transcription")
                issues["empty_transcription"].append(track)

            # 2. No timecoded text
            if (
                track.transcription.strip()
                and not track.transcription_timecoded.strip()
            ):
                track_issues.append("no_timecoded")
                issues["no_timecoded"].append(track)

            # 3. Audio file missing
            audio_path = None
            if track.local_path:
                audio_path = Path(track.local_path.path)
                if not audio_path.exists():
                    track_issues.append("audio_missing")
                    issues["audio_missing"].append(track)
                    audio_path = None

            # Parse timecoded segments for remaining checks
            segments = _parse_timecoded(track.transcription_timecoded) if track.transcription_timecoded else []

            if segments:
                times = [s for s, _ in segments]
                texts = [t for _, t in segments]
                last_ts = times[-1]

                # 4 & 5. Duration-based checks (require ffprobe)
                if not skip_ffprobe and audio_path:
                    duration = _audio_duration(audio_path)
                    if duration and duration > 0:
                        if last_ts < duration * TRUNCATION_RATIO:
                            track_issues.append("truncated")
                            issues["truncated"].append(
                                (track, last_ts, duration)
                            )
                        elif last_ts > duration + DRIFT_MARGIN_SECS:
                            track_issues.append("duration_drift")
                            issues["duration_drift"].append(
                                (track, last_ts, duration)
                            )

                # 6. Non-monotonic timestamps
                for j in range(1, len(times)):
                    if times[j] < times[j - 1]:
                        track_issues.append("non_monotonic")
                        issues["non_monotonic"].append(
                            (track, times[j - 1], times[j], j)
                        )
                        break

                # 7. Low word density (words per minute)
                if last_ts > 0:
                    word_count = len(track.transcription.split())
                    wpm = word_count / (last_ts / 60)
                    if wpm < MIN_WORDS_PER_MINUTE:
                        track_issues.append("low_word_density")
                        issues["low_word_density"].append((track, wpm))

                # 9. Large gaps between consecutive segments
                for j in range(1, len(times)):
                    gap = times[j] - times[j - 1]
                    if gap > GAP_THRESHOLD_SECS:
                        track_issues.append("large_gap")
                        issues["large_gap"].append((track, times[j - 1], times[j], gap))
                        break

            if track_issues:
                flags = ", ".join(track_issues)
                self.stdout.write(
                    self.style.WARNING(f"[{i}/{len(tracks)}] {track.name[:70]} — {flags}")
                )
            else:
                ok += 1
                if i % 100 == 0 or i == len(tracks):
                    self.stdout.write(f"[{i}/{len(tracks)}] checked, {ok} OK so far")

        # Summary
        self.stdout.write("\n--- Summary ---")
        self.stdout.write(f"  OK:                {ok}")
        self.stdout.write(f"  Empty transcription:  {len(issues['empty_transcription'])}")
        self.stdout.write(f"  No timecoded text:    {len(issues['no_timecoded'])}")
        self.stdout.write(f"  Audio file missing:   {len(issues['audio_missing'])}")
        self.stdout.write(f"  Truncated:            {len(issues['truncated'])}")
        self.stdout.write(f"  Duration drift:       {len(issues['duration_drift'])}")
        self.stdout.write(f"  Non-monotonic:        {len(issues['non_monotonic'])}")
        self.stdout.write(f"  Low word density:     {len(issues['low_word_density'])}")
        self.stdout.write(f"  Large gaps (>5min):   {len(issues['large_gap'])}")

        if issues["truncated"]:
            self.stdout.write(self.style.WARNING("\nTruncated (last timestamp < 80% of audio):"))
            for track, last_ts, dur in issues["truncated"]:
                self.stdout.write(
                    f"  [{track.pk}] {track.name[:60]} — last={_fmt(last_ts)}, audio={_fmt(dur)}"
                )

        if issues["duration_drift"]:
            self.stdout.write(self.style.WARNING("\nDuration drift (last timestamp >> audio length):"))
            for track, last_ts, dur in issues["duration_drift"]:
                self.stdout.write(
                    f"  [{track.pk}] {track.name[:60]} — last={_fmt(last_ts)}, audio={_fmt(dur)}"
                )

        if issues["low_word_density"]:
            self.stdout.write(self.style.WARNING("\nLow word density:"))
            for track, wpm in issues["low_word_density"]:
                self.stdout.write(
                    f"  [{track.pk}] {track.name[:60]} — {wpm:.1f} wpm"
                )

        if issues["large_gap"]:
            self.stdout.write(self.style.WARNING("\nLarge timestamp gaps:"))
            for track, t1, t2, gap in issues["large_gap"]:
                self.stdout.write(
                    f"  [{track.pk}] {track.name[:60]} — gap of {_fmt(gap)} between {_fmt(t1)} and {_fmt(t2)}"
                )

        total_issues = sum(
            len(v) for v in issues.values()
            if v and isinstance(v[0], AudioTrack)
        ) + sum(
            len(v) for v in issues.values()
            if v and not isinstance(v[0], AudioTrack)
        )

        if total_issues == 0:
            self.stdout.write(self.style.SUCCESS("\nAll transcriptions look good!"))
