"""
Output writer for transcription results in various formats.
"""
from pathlib import Path
from typing import Optional

from src.core.transcription import TranscriptionResult


class OutputWriter:
    """Writes transcription results to various file formats."""

    def save(
        self,
        result: TranscriptionResult,
        source_path: Path,
        output_format: str,
        output_dir: Optional[Path] = None,
    ) -> Path:
        """
        Save transcription result to file.

        Args:
            result: TranscriptionResult from transcription service
            source_path: Path to the original media file
            output_format: Output format ("txt", "srt", or "vtt")
            output_dir: Optional directory for output. If None, saves next to source.

        Returns:
            Path to the saved file
        """
        source_path = Path(source_path)
        output_format = output_format.lower().strip(".")

        # Determine output path
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{source_path.stem}.{output_format}"
        else:
            output_path = source_path.with_suffix(f".{output_format}")

        # Handle name conflicts
        output_path = self._resolve_conflict(output_path)

        # Generate content based on format
        if output_format == "txt":
            content = self._to_txt(result)
        elif output_format == "srt":
            content = self._to_srt(result)
        elif output_format == "vtt":
            content = self._to_vtt(result)
        else:
            raise ValueError(f"Unsupported format: {output_format}")

        # Write file
        output_path.write_text(content, encoding="utf-8")

        return output_path

    def _resolve_conflict(self, path: Path) -> Path:
        """
        Resolve file name conflicts by adding suffix.

        If file.txt exists, returns file_1.txt, file_2.txt, etc.
        """
        if not path.exists():
            return path

        counter = 1
        stem = path.stem
        suffix = path.suffix
        parent = path.parent

        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1

    def _to_txt(self, result: TranscriptionResult) -> str:
        """
        Convert transcription to plain text format.

        Uses paragraphs if available, otherwise uses plain transcript.
        Includes speaker labels if diarization was enabled.
        """
        if not result.success or not result.transcript:
            return ""

        # If paragraphs available with speaker info, use them
        if result.paragraphs:
            lines = []
            current_speaker = None

            for para in result.paragraphs:
                speaker = para.get("speaker")
                text = para.get("text", "").strip()

                if not text:
                    continue

                # Add speaker label if changed
                if speaker is not None and speaker != current_speaker:
                    current_speaker = speaker
                    lines.append(f"\n[Speaker {speaker + 1}]")

                lines.append(text)

            return "\n".join(lines).strip()

        # Fallback to plain transcript
        return result.transcript.strip()

    def _to_srt(self, result: TranscriptionResult) -> str:
        """
        Convert transcription to SRT subtitle format.

        Format:
        1
        00:00:01,000 --> 00:00:04,500
        Text content here

        2
        00:00:04,500 --> 00:00:08,000
        More text here
        """
        if not result.success:
            return ""

        lines = []
        counter = 1

        # Use utterances if available (preferred for subtitles)
        if result.utterances:
            for utt in result.utterances:
                start = self._format_srt_time(utt["start"])
                end = self._format_srt_time(utt["end"])
                text = utt["text"].strip()

                if not text:
                    continue

                # Add speaker label if available
                speaker = utt.get("speaker")
                if speaker is not None:
                    text = f"[Speaker {speaker + 1}] {text}"

                lines.append(str(counter))
                lines.append(f"{start} --> {end}")
                lines.append(text)
                lines.append("")  # Empty line between entries
                counter += 1

        # Fallback: create from words if no utterances
        elif result.words:
            # Group words into segments of ~10 words or ~5 seconds
            segments = self._group_words_into_segments(result.words)

            for segment in segments:
                if not segment:
                    continue

                start = self._format_srt_time(segment[0]["start"])
                end = self._format_srt_time(segment[-1]["end"])
                text = " ".join(w["word"] for w in segment)

                lines.append(str(counter))
                lines.append(f"{start} --> {end}")
                lines.append(text)
                lines.append("")
                counter += 1

        # Last fallback: single entry with full transcript
        elif result.transcript:
            duration = result.duration_seconds or 60.0
            lines.append("1")
            lines.append(f"00:00:00,000 --> {self._format_srt_time(duration)}")
            lines.append(result.transcript)
            lines.append("")

        return "\n".join(lines)

    def _to_vtt(self, result: TranscriptionResult) -> str:
        """
        Convert transcription to WebVTT subtitle format.

        Format:
        WEBVTT

        00:00:01.000 --> 00:00:04.500
        Text content here

        00:00:04.500 --> 00:00:08.000
        More text here
        """
        if not result.success:
            return "WEBVTT\n"

        lines = ["WEBVTT", ""]

        # Use utterances if available
        if result.utterances:
            for utt in result.utterances:
                start = self._format_vtt_time(utt["start"])
                end = self._format_vtt_time(utt["end"])
                text = utt["text"].strip()

                if not text:
                    continue

                speaker = utt.get("speaker")
                if speaker is not None:
                    text = f"[Speaker {speaker + 1}] {text}"

                lines.append(f"{start} --> {end}")
                lines.append(text)
                lines.append("")

        # Fallback: create from words
        elif result.words:
            segments = self._group_words_into_segments(result.words)

            for segment in segments:
                if not segment:
                    continue

                start = self._format_vtt_time(segment[0]["start"])
                end = self._format_vtt_time(segment[-1]["end"])
                text = " ".join(w["word"] for w in segment)

                lines.append(f"{start} --> {end}")
                lines.append(text)
                lines.append("")

        # Last fallback
        elif result.transcript:
            duration = result.duration_seconds or 60.0
            lines.append(f"00:00:00.000 --> {self._format_vtt_time(duration)}")
            lines.append(result.transcript)
            lines.append("")

        return "\n".join(lines)

    def _format_srt_time(self, seconds: float) -> str:
        """Format time in seconds to SRT format (HH:MM:SS,mmm)."""
        if seconds is None:
            seconds = 0.0

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _format_vtt_time(self, seconds: float) -> str:
        """Format time in seconds to VTT format (HH:MM:SS.mmm)."""
        if seconds is None:
            seconds = 0.0

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    def _group_words_into_segments(
        self,
        words: list[dict],
        max_words: int = 10,
        max_duration: float = 5.0,
    ) -> list[list[dict]]:
        """
        Group words into segments for subtitle display.

        Args:
            words: List of word dictionaries with start, end, word keys
            max_words: Maximum words per segment
            max_duration: Maximum duration in seconds per segment

        Returns:
            List of word groups
        """
        if not words:
            return []

        segments = []
        current_segment = []
        segment_start = None

        for word in words:
            if segment_start is None:
                segment_start = word["start"]

            current_segment.append(word)

            # Check if segment should end
            duration = word["end"] - segment_start
            should_split = (
                len(current_segment) >= max_words
                or duration >= max_duration
            )

            if should_split:
                segments.append(current_segment)
                current_segment = []
                segment_start = None

        # Add remaining words
        if current_segment:
            segments.append(current_segment)

        return segments
