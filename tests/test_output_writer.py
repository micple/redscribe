"""Tests for src/core/output_writer.py"""
import pytest
from pathlib import Path
from src.core.output_writer import OutputWriter
from src.core.transcription import TranscriptionResult


@pytest.fixture
def writer():
    return OutputWriter()


@pytest.fixture
def success_result():
    return TranscriptionResult(
        success=True,
        transcript="Hello world.",
        utterances=[{"start": 0.0, "end": 1.5, "text": "Hello world.", "speaker": 0}],
        duration_seconds=1.5,
    )


@pytest.fixture
def multi_utterance_result():
    return TranscriptionResult(
        success=True,
        transcript="Hello world. How are you.",
        utterances=[
            {"start": 0.0, "end": 1.5, "text": "Hello world.", "speaker": 0},
            {"start": 2.0, "end": 3.5, "text": "How are you.", "speaker": 1},
        ],
        duration_seconds=3.5,
    )


@pytest.fixture
def paragraphs_result():
    return TranscriptionResult(
        success=True,
        transcript="Hello world. Goodbye.",
        paragraphs=[
            {"speaker": 0, "text": "Hello world."},
            {"speaker": 1, "text": "Goodbye."},
        ],
        duration_seconds=3.0,
    )


@pytest.fixture
def words_result():
    return TranscriptionResult(
        success=True,
        transcript="Hello world how are you doing today my friend yes indeed",
        words=[
            {"start": 0.0, "end": 0.5, "word": "Hello"},
            {"start": 0.5, "end": 1.0, "word": "world"},
            {"start": 1.0, "end": 1.5, "word": "how"},
            {"start": 1.5, "end": 2.0, "word": "are"},
            {"start": 2.0, "end": 2.5, "word": "you"},
            {"start": 2.5, "end": 3.0, "word": "doing"},
            {"start": 3.0, "end": 3.5, "word": "today"},
            {"start": 3.5, "end": 4.0, "word": "my"},
            {"start": 4.0, "end": 4.5, "word": "friend"},
            {"start": 4.5, "end": 5.0, "word": "yes"},
            {"start": 5.0, "end": 5.5, "word": "indeed"},
        ],
        duration_seconds=5.5,
    )


@pytest.fixture
def transcript_only_result():
    return TranscriptionResult(
        success=True,
        transcript="Just a plain transcript with no timestamps.",
        duration_seconds=4.0,
    )


class TestTxt:
    def test_creates_file(self, writer, success_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        o = writer.save(success_result, s, "txt")
        assert o.exists() and o.suffix == ".txt"

    def test_contains_transcript(self, writer, success_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        assert "Hello" in writer.save(success_result, s, "txt").read_text(encoding="utf-8")

    def test_empty_result(self, writer, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        assert writer.save(TranscriptionResult(success=False), s, "txt").read_text(encoding="utf-8") == ""

    def test_paragraphs_with_speaker_labels(self, writer, paragraphs_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        text = writer.save(paragraphs_result, s, "txt").read_text(encoding="utf-8")
        assert "[Speaker 1]" in text
        assert "[Speaker 2]" in text
        assert "Hello world." in text
        assert "Goodbye." in text

    def test_paragraphs_same_speaker_no_duplicate_label(self, writer, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        r = TranscriptionResult(
            success=True,
            transcript="Hello. Goodbye.",
            paragraphs=[
                {"speaker": 0, "text": "Hello."},
                {"speaker": 0, "text": "Goodbye."},
            ],
            duration_seconds=2.0,
        )
        text = writer.save(r, s, "txt").read_text(encoding="utf-8")
        assert text.count("[Speaker 1]") == 1

    def test_paragraphs_empty_text_skipped(self, writer, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        r = TranscriptionResult(
            success=True,
            transcript="Hello.",
            paragraphs=[
                {"speaker": 0, "text": ""},
                {"speaker": 0, "text": "Hello."},
            ],
            duration_seconds=1.0,
        )
        text = writer.save(r, s, "txt").read_text(encoding="utf-8")
        assert "Hello." in text

    def test_plain_transcript_fallback(self, writer, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        r = TranscriptionResult(success=True, transcript="  Just text  ")
        text = writer.save(r, s, "txt").read_text(encoding="utf-8")
        assert text == "Just text"


class TestSrt:
    def test_valid(self, writer, success_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        assert "-->" in writer.save(success_result, s, "srt").read_text(encoding="utf-8")

    def test_timestamps(self, writer, success_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        assert "00:00:00,000" in writer.save(success_result, s, "srt").read_text(encoding="utf-8")

    def test_speaker_label_in_srt(self, writer, multi_utterance_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        text = writer.save(multi_utterance_result, s, "srt").read_text(encoding="utf-8")
        assert "[Speaker 1]" in text
        assert "[Speaker 2]" in text

    def test_srt_from_words_fallback(self, writer, words_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        words_result.utterances = None
        text = writer.save(words_result, s, "srt").read_text(encoding="utf-8")
        assert "-->" in text
        assert "Hello" in text

    def test_srt_transcript_only_fallback(self, writer, transcript_only_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        text = writer.save(transcript_only_result, s, "srt").read_text(encoding="utf-8")
        assert "1" in text
        assert "-->" in text
        assert "Just a plain transcript" in text

    def test_srt_empty_utterance_skipped(self, writer, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        r = TranscriptionResult(
            success=True,
            transcript="text",
            utterances=[
                {"start": 0.0, "end": 1.0, "text": "  ", "speaker": 0},
                {"start": 1.0, "end": 2.0, "text": "Real text", "speaker": 0},
            ],
            duration_seconds=2.0,
        )
        text = writer.save(r, s, "srt").read_text(encoding="utf-8")
        assert "Real text" in text
        assert text.count("-->") == 1

    def test_srt_failed_result_empty(self, writer, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        r = TranscriptionResult(success=False)
        text = writer.save(r, s, "srt").read_text(encoding="utf-8")
        assert text == ""



class TestVtt:
    def test_header(self, writer, success_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        assert writer.save(success_result, s, "vtt").read_text(encoding="utf-8").startswith("WEBVTT")

    def test_vtt_ts(self, writer, success_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        assert "-->" in writer.save(success_result, s, "vtt").read_text(encoding="utf-8")

    def test_vtt_failed(self, writer, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        r = TranscriptionResult(success=False)
        text = writer.save(r, s, "vtt").read_text(encoding="utf-8")
        assert text.startswith("WEBVTT")

    def test_vtt_words_fallback(self, writer, words_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        words_result.utterances = None
        text = writer.save(words_result, s, "vtt").read_text(encoding="utf-8")
        assert "WEBVTT" in text
        assert "-->" in text
        assert "Hello" in text

    def test_vtt_transcript_fallback(self, writer, transcript_only_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        text = writer.save(transcript_only_result, s, "vtt").read_text(encoding="utf-8")
        assert "WEBVTT" in text
        assert "-->" in text
        assert "Just a plain transcript" in text

    def test_vtt_speakers(self, writer, multi_utterance_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        text = writer.save(multi_utterance_result, s, "vtt").read_text(encoding="utf-8")
        assert "[Speaker 1]" in text
        assert "[Speaker 2]" in text

    def test_vtt_empty_utt(self, writer, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        r = TranscriptionResult(
            success=True, transcript="text",
            utterances=[
                {"start": 0.0, "end": 1.0, "text": "   "},
                {"start": 1.0, "end": 2.0, "text": "Real text"},
            ], duration_seconds=2.0)
        text = writer.save(r, s, "vtt").read_text(encoding="utf-8")
        assert "Real text" in text


class TestCustomDir:
    def test_custom_dir(self, writer, success_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        out = tmp_path / "output"
        o = writer.save(success_result, s, "txt", output_dir=out)
        assert out.exists() and o.parent == out

    def test_unsupported(self, writer, success_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        with pytest.raises(ValueError, match="Unsupported format"):
            writer.save(success_result, s, "docx")


class TestResolveConflict:
    def test_no_conflict(self, writer, success_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        o = writer.save(success_result, s, "txt")
        assert o.name == "a.txt"

    def test_conflict_adds_suffix(self, writer, success_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        (tmp_path / "a.txt").write_text("existing", encoding="utf-8")
        o = writer.save(success_result, s, "txt")
        assert o.name == "a_1.txt"

    def test_multiple_conflicts(self, writer, success_result, tmp_path):
        s = tmp_path / "a.mp3"
        s.write_bytes(b"f")
        (tmp_path / "a.txt").write_text("existing", encoding="utf-8")
        (tmp_path / "a_1.txt").write_text("existing", encoding="utf-8")
        o = writer.save(success_result, s, "txt")
        assert o.name == "a_2.txt"


class TestFormatTime:
    def test_srt_time(self, writer):
        assert writer._format_srt_time(3661.5) == "01:01:01,500"

    def test_vtt_time(self, writer):
        assert writer._format_vtt_time(3661.5) == "01:01:01.500"

    def test_srt_none(self, writer):
        assert writer._format_srt_time(None) == "00:00:00,000"

    def test_vtt_none(self, writer):
        assert writer._format_vtt_time(None) == "00:00:00.000"

    def test_srt_zero(self, writer):
        assert writer._format_srt_time(0.0) == "00:00:00,000"


class TestGroupWords:
    def test_empty(self, writer):
        assert writer._group_words_into_segments([]) == []

    def test_splits_by_max_words(self, writer):
        words = [{"start": float(i), "end": float(i)+0.4, "word": f"w{i}"} for i in range(25)]
        segments = writer._group_words_into_segments(words, max_words=10, max_duration=999.0)
        assert len(segments) == 3
        assert len(segments[0]) == 10

    def test_splits_by_duration(self, writer):
        words = [
            {"start": 0.0, "end": 2.0, "word": "a"},
            {"start": 2.0, "end": 4.0, "word": "b"},
            {"start": 4.0, "end": 5.5, "word": "c"},
            {"start": 5.5, "end": 7.0, "word": "d"},
        ]
        segments = writer._group_words_into_segments(words, max_words=999, max_duration=5.0)
        assert len(segments) >= 2

    def test_single_word(self, writer):
        words = [{"start": 0.0, "end": 0.5, "word": "hello"}]
        segments = writer._group_words_into_segments(words)
        assert len(segments) == 1
