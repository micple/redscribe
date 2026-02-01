"""
YouTube audio downloader using yt-dlp.

Downloads audio from YouTube videos, playlists, and channels as MP3.
"""
import re
import uuid
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor

try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False

from config import YOUTUBE_TEMP_DIR
from src.utils.temp_file_manager import TempFileManager


class YtDlpNotFoundError(Exception):
    """Raised when yt-dlp is not installed."""
    pass


@dataclass
class VideoInfo:
    """Information about a YouTube video."""
    url: str
    title: str
    duration_seconds: int = 0
    channel: str = ""
    thumbnail: str = ""


@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    path: Optional[Path] = None
    title: str = ""
    error: Optional[str] = None
    duration_seconds: int = 0


@dataclass
class FetchResult:
    """Result of fetching video information."""
    videos: list
    url_type: str = "video"  # video, playlist, channel
    playlist_title: str = ""
    channel_name: str = ""


@dataclass
class ChannelPlaylistInfo:
    """Information about a playlist from a channel."""
    url: str
    title: str
    playlist_id: str
    video_count: int = 0
    thumbnail: str = ""


@dataclass
class ChannelContent:
    """Content extracted from a YouTube channel."""
    channel_name: str
    playlists: list  # List of ChannelPlaylistInfo
    loose_videos: list  # List of VideoInfo (videos not in any playlist)


class YouTubeDownloader:
    """
    Downloads audio from YouTube as MP3.

    Usage:
        downloader = YouTubeDownloader()

        # Get video info (for single video or playlist)
        videos = downloader.extract_info(url)

        # Download audio
        result = downloader.download_audio(video_url)
        if result.success:
            # Use result.path for transcription
            pass

        # Cleanup
        downloader.cleanup(result.path)
    """

    # YouTube URL patterns
    VIDEO_PATTERNS = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
    ]
    PLAYLIST_PATTERN = r'youtube\.com/playlist\?list=([a-zA-Z0-9_-]+)'
    CHANNEL_PATTERNS = [
        r'youtube\.com/@([^/\?]+)',
        r'youtube\.com/channel/([a-zA-Z0-9_-]+)',
        r'youtube\.com/c/([^/\?]+)',
    ]

    def __init__(self, temp_dir: Path = YOUTUBE_TEMP_DIR):
        if not HAS_YTDLP:
            raise YtDlpNotFoundError(
                "yt-dlp is not installed.\n"
                "Run: pip install yt-dlp"
            )
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.temp_manager = TempFileManager(self.temp_dir)

    def detect_url_type(self, url: str) -> str:
        """
        Detect the type of YouTube URL.

        Returns: 'video', 'playlist', 'channel', or 'unknown'
        """
        if any(re.search(p, url) for p in self.VIDEO_PATTERNS):
            # Check if it's also a playlist URL (video in playlist)
            if 'list=' in url:
                return 'playlist'
            return 'video'
        if re.search(self.PLAYLIST_PATTERN, url):
            return 'playlist'
        if any(re.search(p, url) for p in self.CHANNEL_PATTERNS):
            return 'channel'
        return 'unknown'

    def _normalize_playlist_url(self, url: str) -> str:
        """
        Convert video+playlist URL to pure playlist URL.

        Example:
        youtube.com/watch?v=xxx&list=yyy -> youtube.com/playlist?list=yyy
        """
        # Extract playlist ID from URL
        match = re.search(r'list=([a-zA-Z0-9_-]+)', url)
        if match:
            playlist_id = match.group(1)
            return f"https://www.youtube.com/playlist?list={playlist_id}"
        return url

    def extract_info(
        self,
        url: str,
        max_videos: int = 100,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> FetchResult:
        """
        Extract video information from URL.

        For single video: returns FetchResult with one VideoInfo
        For playlist/channel: returns FetchResult with all VideoInfo

        Args:
            url: YouTube URL
            max_videos: Maximum videos to extract from playlist/channel
            on_progress: Callback for progress updates

        Returns:
            FetchResult with videos and metadata (playlist title, channel name)
        """
        # Convert video+playlist URL to pure playlist URL
        url_type = self.detect_url_type(url)
        if url_type == 'playlist' and 'watch?v=' in url:
            url = self._normalize_playlist_url(url)

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Don't download, just get info
            'playlistend': max_videos,
        }

        if on_progress:
            on_progress("Fetching video information...")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                if info is None:
                    return FetchResult(videos=[], url_type=url_type)

                # Check if it's a playlist or single video
                if 'entries' in info:
                    # Playlist or channel
                    videos = []
                    entries = list(info.get('entries', []))
                    playlist_title = info.get('title', '')
                    channel_name = info.get('channel', '') or info.get('uploader', '')

                    for i, entry in enumerate(entries):
                        if entry is None:
                            continue

                        video_url = entry.get('url') or entry.get('webpage_url')
                        if not video_url:
                            # Build URL from video ID
                            video_id = entry.get('id')
                            if video_id:
                                video_url = f"https://www.youtube.com/watch?v={video_id}"
                            else:
                                continue

                        # Get channel from entry or fall back to playlist-level channel
                        entry_channel = entry.get('channel', '') or channel_name

                        videos.append(VideoInfo(
                            url=video_url,
                            title=entry.get('title', f'Video {i+1}'),
                            duration_seconds=entry.get('duration', 0) or 0,
                            channel=entry_channel,
                            thumbnail=entry.get('thumbnail', ''),
                        ))

                        if on_progress and len(videos) % 10 == 0:
                            on_progress(f"Found {len(videos)} videos...")

                    return FetchResult(
                        videos=videos,
                        url_type=url_type,
                        playlist_title=playlist_title,
                        channel_name=channel_name,
                    )
                else:
                    # Single video
                    channel_name = info.get('channel', '') or info.get('uploader', '')
                    videos = [VideoInfo(
                        url=url,
                        title=info.get('title', 'Unknown'),
                        duration_seconds=info.get('duration', 0) or 0,
                        channel=channel_name,
                        thumbnail=info.get('thumbnail', ''),
                    )]
                    return FetchResult(
                        videos=videos,
                        url_type=url_type,
                        playlist_title='',
                        channel_name=channel_name,
                    )

        except yt_dlp.DownloadError as e:
            error_msg = str(e)
            if 'Private video' in error_msg:
                raise ValueError("This video is private and cannot be accessed.")
            elif 'Video unavailable' in error_msg:
                raise ValueError("This video is unavailable.")
            elif 'Sign in' in error_msg:
                raise ValueError("This video requires sign-in to access.")
            else:
                raise ValueError(f"Cannot access video: {error_msg}")
        except Exception as e:
            raise ValueError(f"Failed to fetch video info: {str(e)}")

    def download_audio(
        self,
        url: str,
        on_progress: Optional[Callable[[float, str], None]] = None
    ) -> DownloadResult:
        """
        Download audio from YouTube video as MP3.

        Args:
            url: YouTube video URL
            on_progress: Callback(percent, status) for progress updates

        Returns:
            DownloadResult with path to downloaded MP3
        """
        # Generate unique filename to avoid conflicts
        file_id = str(uuid.uuid4())[:8]
        output_template = str(self.temp_dir / f"%(title).50s_{file_id}.%(ext)s")

        def progress_hook(d):
            if on_progress and d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    percent = (downloaded / total) * 100
                    on_progress(percent, "Downloading...")
            elif on_progress and d['status'] == 'finished':
                on_progress(100, "Converting to MP3...")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [progress_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

                if info is None:
                    return DownloadResult(
                        success=False,
                        error="Could not extract video information"
                    )

                title = info.get('title', 'Unknown')
                duration = info.get('duration', 0) or 0

                # Find the downloaded file
                # yt-dlp converts to MP3, so we need to find the actual file
                expected_name = ydl.prepare_filename(info)
                # Replace extension with .mp3
                mp3_path = Path(expected_name).with_suffix('.mp3')

                if not mp3_path.exists():
                    # Try finding any MP3 with our file_id
                    matches = list(self.temp_dir.glob(f"*_{file_id}.mp3"))
                    if matches:
                        mp3_path = matches[0]
                    else:
                        return DownloadResult(
                            success=False,
                            error="Downloaded file not found"
                        )

                return DownloadResult(
                    success=True,
                    path=mp3_path,
                    title=title,
                    duration_seconds=duration,
                )

        except yt_dlp.DownloadError as e:
            error_msg = str(e)
            if 'Private video' in error_msg:
                return DownloadResult(success=False, error="Video is private")
            elif 'Video unavailable' in error_msg:
                return DownloadResult(success=False, error="Video unavailable")
            elif 'Sign in' in error_msg:
                return DownloadResult(success=False, error="Requires sign-in")
            elif 'ffmpeg' in error_msg.lower():
                return DownloadResult(success=False, error="FFmpeg not found")
            else:
                return DownloadResult(success=False, error=str(e)[:100])
        except Exception as e:
            return DownloadResult(success=False, error=str(e)[:100])

    def cleanup(self, path: Path) -> None:
        """Delete a downloaded file."""
        if path:
            self.temp_manager.cleanup_file(Path(path))

    def cleanup_all(self) -> None:
        """Delete all temporary files in the YouTube temp directory."""
        self.temp_manager.cleanup_all()

    def extract_channel_content(
        self,
        channel_url: str,
        max_playlists: int = 50,
        max_loose_videos: int = 100,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> ChannelContent:
        """
        Extract playlists and loose videos from a YouTube channel.

        Args:
            channel_url: YouTube channel URL
            max_playlists: Maximum playlists to fetch
            max_loose_videos: Maximum loose videos to fetch
            on_progress: Callback for progress updates

        Returns:
            ChannelContent with playlists and loose videos
        """
        channel_url = channel_url.rstrip('/')
        channel_name = ""
        playlists = []
        loose_videos = []

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'ignoreerrors': True,
        }

        # Step 1: Fetch playlists from /playlists tab
        if on_progress:
            on_progress("Fetching channel playlists...")

        playlists_url = channel_url + '/playlists'
        try:
            with yt_dlp.YoutubeDL({**ydl_opts, 'playlistend': max_playlists}) as ydl:
                info = ydl.extract_info(playlists_url, download=False)

                if info:
                    channel_name = info.get('channel') or info.get('uploader') or ''

                    for entry in info.get('entries', []):
                        if entry is None:
                            continue

                        playlist_url = entry.get('url') or entry.get('webpage_url')
                        if not playlist_url:
                            playlist_id = entry.get('id')
                            if playlist_id:
                                playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
                            else:
                                continue

                        playlists.append(ChannelPlaylistInfo(
                            url=playlist_url,
                            title=entry.get('title', 'Unknown Playlist'),
                            playlist_id=entry.get('id', ''),
                            video_count=entry.get('playlist_count') or entry.get('n_entries') or 0,
                            thumbnail=entry.get('thumbnail', ''),
                        ))

                    if on_progress:
                        on_progress(f"Found {len(playlists)} playlists...")

        except Exception as e:
            if on_progress:
                on_progress(f"Error fetching playlists: {str(e)[:30]}")

        # Step 2: Fetch loose videos from /videos tab
        if on_progress:
            on_progress("Fetching channel videos...")

        videos_url = channel_url + '/videos'
        try:
            with yt_dlp.YoutubeDL({**ydl_opts, 'playlistend': max_loose_videos}) as ydl:
                info = ydl.extract_info(videos_url, download=False)

                if info:
                    if not channel_name:
                        channel_name = info.get('channel') or info.get('uploader') or ''

                    for entry in info.get('entries', []):
                        if entry is None:
                            continue

                        video_url = entry.get('url') or entry.get('webpage_url')
                        if not video_url:
                            video_id = entry.get('id')
                            if video_id:
                                video_url = f"https://www.youtube.com/watch?v={video_id}"
                            else:
                                continue

                        loose_videos.append(VideoInfo(
                            url=video_url,
                            title=entry.get('title', 'Unknown Video'),
                            duration_seconds=entry.get('duration', 0) or 0,
                            channel=channel_name,
                            thumbnail=entry.get('thumbnail', ''),
                        ))

                    if on_progress:
                        on_progress(f"Found {len(loose_videos)} videos...")

        except Exception as e:
            if on_progress:
                on_progress(f"Error fetching videos: {str(e)[:30]}")

        return ChannelContent(
            channel_name=channel_name,
            playlists=playlists,
            loose_videos=loose_videos,
        )

    @staticmethod
    def format_duration(seconds) -> str:
        """Format duration in seconds to human-readable string."""
        if seconds is None or seconds <= 0:
            return "?"

        # Convert to int (yt-dlp can return float)
        seconds = int(seconds)

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
