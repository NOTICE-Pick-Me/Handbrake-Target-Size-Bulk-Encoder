import sys
import os
import subprocess
import json  # Import json for JSON operations
import sqlite3
import re
import pycountry
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer, QPoint, QEvent  # Added QEvent
from PyQt5.QtGui import QFont, QIcon, QCursor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTreeWidget, QTreeWidgetItem, QLabel, QLineEdit, QComboBox, QTextEdit,
    QMessageBox, QSizePolicy, QFileDialog, QAbstractItemView, QProgressBar,
    QCheckBox, QSplitter, QMenu, QAction, QDialog, QDialogButtonBox, QListWidget,
    QListWidgetItem, QGridLayout, QToolTip, QSpacerItem  # QToolTip already imported
)

# ---------------------- Global Headline Variables ----------------------

# Headline for Destination Directory Section
DEST_DIR_HEADLINE = {
    'text': "📂 Destination Directory",
    'font_size': 11,
    'bold': True,
    'color': "#2E8B57"  # SeaGreen
}

# Headline for Media List Section
MEDIA_LIST_HEADLINE = {
    'text': "🎬 Media Library",
    'font_size': 11,
    'bold': True,
    'color': "#2E8B57"
}

# Headline for Encoding Progress Section
ENCODING_PROGRESS_HEADLINE = {
    'text': "⏳ Encoding Progress",
    'font_size': 11,
    'bold': True,
    'color': "#2E8B57"
}

# Headline for HandBrake Output Section
HANDBRAKE_OUTPUT_HEADLINE = {
    'text': "⚙️ HandBrake Output",
    'font_size': 11,
    'bold': True,
    'color': "#2E8B57"
}

# -------------------------------------------------------------------------

# Global variables for component sizes
MEDIA_LIST_WIDTH = 850
MEDIA_LIST_HEIGHT = 350

PROGRESS_AREA_WIDTH = 850
PROGRESS_AREA_HEIGHT = 250

OUTPUT_AREA_WIDTH = 850
OUTPUT_AREA_HEIGHT = 150

DEST_INPUT_WIDTH = 750
DEST_BROWSE_BTN_WIDTH = 100  # Adjust as needed

# Font sizes for the widgets
FONT_SIZE_MEDIA_LIST = 9    # Adjust as needed
FONT_SIZE_PROGRESS_AREA = 8.5  # Adjust as needed
FONT_SIZE_OUTPUT_AREA = 8.5    # Adjust as needed
FONT_SIZE_DEST_INPUT = 9    # Adjust as needed
FONT_SIZE_LABELS = 9        # New variable for label font sizes

# Font size and dimensions for all ComboBoxes
COMBO_BOX_WIDTH = 150  # Adjust as needed
COMBO_BOX_HEIGHT = 25  # Adjust as needed
FONT_SIZE_COMBO_BOX = 8.5  # Adjust as needed

# Column indices
COL_FILENAME = 0
COL_DURATION = 1
COL_VIDEO = 2
COL_AUDIO = 3
COL_SIZE = 4

# Default column widths (will be overridden by stored values if available)
DEFAULT_COL_WIDTHS = {
    COL_FILENAME: 250,
    COL_DURATION: 80,
    COL_VIDEO: 150,
    COL_AUDIO: 150,
    COL_SIZE: 80
}

# Global variable for per-file output prints
PER_FILE_OUTPUT_ONLY = True  # Set to True to clear progress and output before each file

# Increased font size for better visibility
FONT_SIZE_INFO_PANEL = 8.1

def get_full_language_name(language_str):
    """
    Converts language codes to their full language names using pycountry.
    If the language_str is already a full name or unknown, it returns it as is.
    """
    # Split multiple languages if present (e.g., 'en,fr')
    languages = [lang.strip() for lang in language_str.split(',')]
    full_languages = []
    for lang in languages:
        if not lang:
            continue  # Skip empty strings
        # Attempt to get the language by alpha_2 code
        language = pycountry.languages.get(alpha_2=lang.lower())
        if language:
            full_name = language.name
        else:
            # Attempt to get the language by alpha_3 code
            language = pycountry.languages.get(alpha_3=lang.lower())
            if language:
                full_name = language.name
            else:
                # Attempt to get the language by name
                try:
                    language = pycountry.languages.lookup(lang)
                    full_name = language.name
                except LookupError:
                    full_name = lang  # Fallback to original string if not found
        full_languages.append(full_name)
    # Join multiple languages back into a string
    return ', '.join(full_languages)

class WorkerSignals(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal()

class CheckMediaWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    clear_progress = pyqtSignal()

    def __init__(self, media_files, mediainfo_exe, mkvpropedit_exe, per_file_output_only=False):
        super().__init__()
        self.media_files = media_files
        self.mediainfo_exe = mediainfo_exe
        self.mkvpropedit_exe = mkvpropedit_exe
        self.per_file_output_only = per_file_output_only

    def run(self):
        self.progress.emit("🚀 Starting media check...\n")

        for idx, media in enumerate(self.media_files, start=1):
            file_path = media['path']
            file_name = os.path.basename(file_path)

            if self.per_file_output_only:
                self.clear_progress.emit()
                self.progress.emit("🚀 Starting media check...\n")

            self.progress.emit(f"Checking: {file_name}")

            needs_update = self.check_needs_update(file_path)
            if not needs_update:
                self.progress.emit(f"✅ No update needed for {file_name}\n")
                continue

            attempts = 0
            max_attempts = 2
            success = False  # Initialize success flag
            while needs_update and attempts < max_attempts:
                self.progress.emit(f"🔄 Updating bitrate for {file_name} (Attempt {attempts + 1})")
                update_success = self.update_duration(file_path)
                if update_success:
                    needs_update = self.check_needs_update(file_path)
                    if not needs_update:
                        self.progress.emit(f"✅ Successfully updated bitrate for {file_name} after {attempts + 1} attempts\n")
                        success = True  # Mark as success
                        break
                else:
                    self.progress.emit(f"❌ Failed to update bitrate for {file_name} on attempt {attempts + 1}\n")
                    break
                attempts += 1
            if not success and needs_update:
                self.progress.emit(f"❌ Failed to update bitrate for {file_name} after {attempts} attempts\n")

        self.progress.emit("✅ Media check completed.\n")
        self.finished.emit()

    def check_needs_update(self, file_path):
        """
        Check if the media file needs bitrate information updating.
        Returns True if either video or audio bitrate is "N/A" or missing.
        """
        try:
            output = subprocess.check_output(
                [self.mediainfo_exe, '--Output=JSON', file_path],
                encoding='utf-8',
                errors='replace',
                text=True
            )
            data = json.loads(output)
            tracks = data.get('media', {}).get('track', [])

            # Initialize flags
            video_bitrate_missing = False
            audio_bitrate_missing = False

            for track in tracks:
                if track.get('@type') == 'Video':
                    bitrate = track.get('BitRate')
                    if not bitrate or str(bitrate).lower() == "n/a":
                        video_bitrate_missing = True
                elif track.get('@type') == 'Audio':
                    bitrate = track.get('BitRate')
                    if not bitrate or str(bitrate).lower() == "n/a":
                        audio_bitrate_missing = True

            return video_bitrate_missing or audio_bitrate_missing
        except Exception as e:
            self.progress.emit(f"Error checking {file_path}: {e}")
            return False

    def update_duration(self, file_path):
        """
        Update the duration and bitrate information of the media file using mkvpropedit.
        """
        try:
            for attempt in range(2):  # Run mkvpropedit twice
                result = subprocess.run(
                    [self.mkvpropedit_exe, file_path, '--add-track-statistics-tags'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding='utf-8',
                    errors='replace',
                    text=True
                )
                if result.returncode != 0:
                    self.progress.emit(f"Error updating {file_path} on attempt {attempt + 1}: {result.stderr}")
                    return False
            return True
        except Exception as e:
            self.progress.emit(f"Exception updating {file_path}: {e}")
            return False

class EncodingWorker(QThread):
    progress = pyqtSignal(str)
    handbrake_output = pyqtSignal(str)
    overall_progress = pyqtSignal(int)
    current_file = pyqtSignal(str)
    current_file_progress = pyqtSignal(int)  # Signal for current file progress percentage
    clear_progress = pyqtSignal()  # New signal to clear progress areas
    finished = pyqtSignal()
    delete_file_signal = pyqtSignal(str, str)  # file_path, delete_source_files_option

    def __init__(self, media_files, handbrake_cli, mediainfo_exe, target_size_mb, audio_bitrate,
                 preset_file, preset_name, destination_folder, per_file_output_only, delete_source_files,
                 selected_encoder, selected_audio_encoder, process_priority, selected_audio_tracks, variable_bitrate=False,
                 ffmpeg_exe=None, multi_pass=False):
        super().__init__()
        self.media_files = media_files
        self.handbrake_cli = handbrake_cli
        self.mediainfo_exe = mediainfo_exe
        self.target_size_mb = target_size_mb
        self.audio_bitrate = audio_bitrate  # Can be a comma-separated string like "320,192"
        self.preset_file = preset_file
        self.preset_name = preset_name
        self.destination_folder = destination_folder
        self.total_files = len(media_files)
        self.processed_files = 0
        self.per_file_output_only = per_file_output_only
        self.delete_source_files = delete_source_files
        self.selected_encoder = selected_encoder
        self.selected_audio_encoder = selected_audio_encoder
        self.process_priority = process_priority
        self.selected_audio_tracks = selected_audio_tracks  # List[List[int]]
        self.variable_bitrate = variable_bitrate  # Existing attribute
        self.ffmpeg_exe = ffmpeg_exe  # Add this line to store ffmpeg_exe
        self.multi_pass = multi_pass
        self.hardware_encoders = ['nvenc_h264', 'nvenc_h265', 'nvenc_h265_10bit']  # Define hardware encoders

    def is_hardware_encoder(self):
        return self.selected_encoder in self.hardware_encoders

    def run(self):
        self.progress.emit("🚀 Starting encoding...\n")
        self.processed_files = 0  # Ensure it's reset at the start

        for idx, media in enumerate(self.media_files, start=1):
            if self.per_file_output_only:
                self.clear_progress.emit()
                self.progress.emit("🚀 Starting encoding...\n")

            file_path = media['path']
            file_name = os.path.basename(file_path)
            self.current_file.emit(f"Encoding File {idx} of {self.total_files}: {file_name}")
            self.progress.emit(f"Processing: {file_name}")
            self.current_file_progress.emit(0)  # Reset current file progress

            # Get duration
            duration = self.get_duration(file_path)
            if duration is None:
                self.progress.emit(f"❌ Error getting duration for {file_name}\n")
                self.update_overall_progress(self.processed_files, 0)
                continue

            # Determine audio bitrate
            if self.selected_audio_encoder == 'copy':
                # Get audio bitrate from source
                audio_bitrate_total = self.get_audio_bitrate(file_path)
                if audio_bitrate_total is None:
                    self.progress.emit(f"❌ Error getting audio bitrate for {file_name}\n")
                    self.update_overall_progress(self.processed_files, 0)
                    continue
                audio_bitrate_info = f"{audio_bitrate_total} kbps (source, copy)"
                selected_bitrate_values = [str(audio_bitrate_total)]  # Single value as a string
            else:
                if self.audio_bitrate:
                    # Split the bitrate string into a list to validate each value
                    bitrate_values = [bitrate.strip() for bitrate in self.audio_bitrate.split(',')]
                    try:
                        # Validate that each bitrate is an integer
                        bitrate_int_values = [int(bitrate) for bitrate in bitrate_values]
                        audio_bitrate_info = f"{', '.join(bitrate_values)} kbps (specified)"
                    except ValueError:
                        self.progress.emit(f"❌ Invalid audio bitrate specified for {file_name}. Ensure all values are integers separated by commas.\n")
                        self.update_overall_progress(self.processed_files, 0)
                        continue

                    # **New Code: Extract only the bitrate values for the selected audio tracks**
                    selected_tracks = self.selected_audio_tracks[idx - 1]  # Assuming idx starts at 1
                    selected_bitrate_values = [bitrate_values[i] for i in selected_tracks if i < len(bitrate_values)]

                    # **Handle cases where selected_tracks might exceed the number of bitrate_values**
                    if len(selected_bitrate_values) != len(selected_tracks):
                        self.progress.emit(f"❌ Mismatch between selected audio tracks and bitrate values for {file_name}.\n")
                        self.update_overall_progress(self.processed_files, 0)
                        continue
                else:
                    # Require the user to specify audio bitrate when encoder is not 'copy'
                    self.progress.emit(f"❌ No audio bitrate specified for {file_name} while using encoder '{self.selected_audio_encoder}'.\n")
                    self.update_overall_progress(self.processed_files, 0)
                    continue

            # Calculate video bitrate using only selected audio bitrates
            video_bitrate = self.calculate_video_bitrate(duration, self.target_size_mb, selected_bitrate_values)
            if video_bitrate is None:
                self.progress.emit(f"❌ Failed to calculate video bitrate for {file_name}\n")
                self.update_overall_progress(self.processed_files, 0)
                continue

            # Prepare summary of encoding settings
            duration_formatted = self.format_duration(duration)
            encoding_summary = (
                f"   • Duration: {duration_formatted}\n"
                f"   • Target Size: {self.target_size_mb} MB\n"
                f"   • Audio Bitrate: {audio_bitrate_info}\n"
                f"   • Calculated Video Bitrate: {video_bitrate} kbps\n"
                f"   • Preset: {self.preset_name}\n"
                f"   • Encoder: {self.selected_encoder}\n"
                f"   • Audio Encoder: {self.selected_audio_encoder}\n"
            )

            # Now, handle variable_bitrate
            if self.variable_bitrate:
                # Estimate RF value
                estimated_rf_value = self.estimate_rf_value(file_path, float(self.target_size_mb), selected_bitrate_values)
                if estimated_rf_value is None:
                    self.progress.emit(f"❌ Failed to estimate RF value for {file_name}\n")
                    self.update_overall_progress(self.processed_files, 0)
                    continue
                encoding_summary = (
                    f"   • Duration: {duration_formatted}\n"
                    f"   • Target Size: {self.target_size_mb} MB\n"
                    f"   • Audio Bitrate: {audio_bitrate_info}\n"
                    f"   • Estimated RF Value: {estimated_rf_value}\n"
                    f"   • Preset: {self.preset_name}\n"
                    f"   • Encoder: {self.selected_encoder}\n"
                    f"   • Audio Encoder: {self.selected_audio_encoder}\n"
                )
            else:
                # Calculate video bitrate
                video_bitrate = self.calculate_video_bitrate(duration, self.target_size_mb, selected_bitrate_values)
                if video_bitrate is None:
                    self.progress.emit(f"❌ Failed to calculate video bitrate for {file_name}\n")
                    self.update_overall_progress(self.processed_files, 0)
                    continue
                encoding_summary = (
                    f"   • Duration: {duration_formatted}\n"
                    f"   • Target Size: {self.target_size_mb} MB\n"
                    f"   • Audio Bitrate: {audio_bitrate_info}\n"
                    f"   • Calculated Video Bitrate: {video_bitrate} kbps\n"
                    f"   • Preset: {self.preset_name}\n"
                    f"   • Encoder: {self.selected_encoder}\n"
                    f"   • Audio Encoder: {self.selected_audio_encoder}\n"
                )

            self.progress.emit(encoding_summary)

            # Prepare HandBrakeCLI command
            output_file = self.get_output_file_path(file_path)

            # Construct the base command
            command = [
                self.handbrake_cli,
                '-i', file_path,
                '-o', output_file,
            ]

            # If preset_file and preset_name are specified, include them
            if self.preset_file and self.preset_name:
                command.extend([
                    '--preset-import-file', self.preset_file,
                    '-Z', self.preset_name,
                ])

            # Add video bitrate or RF value
            if self.variable_bitrate:
                # Use estimated RF value
                command.extend([
                    '-q', str(estimated_rf_value),
                ])
            else:
                # Use calculated video bitrate
                command.extend([
                    '-b', str(video_bitrate),
                ])

            # Add multi-pass option if variable bitrate is not used and hardware encoder is not selected
            if not self.variable_bitrate and not self.is_hardware_encoder():
                if self.multi_pass:
                    command.append('--multi-pass')
                else:
                    command.append('--no-multi-pass')

            # If preset is 'None', include '--all-subtitles'
            if self.preset_name is None:
                command.append('--all-subtitles')

            # Add video encoder if specified and not 'None'
            if self.selected_encoder and self.selected_encoder != 'None':
                command.extend(['-e', self.selected_encoder])
                
            # Handle selected audio tracks
            selected_tracks = self.selected_audio_tracks[idx - 1]  # Assuming idx starts at 1
            if selected_tracks:
                # Convert 0-based indices to 1-based
                selected_tracks_1_based = [str(i + 1) for i in selected_tracks]
                audio_tracks_str = ','.join(selected_tracks_1_based)
                command.extend(['-a', audio_tracks_str])

            # Set audio bitrate if specified, audio tracks are selected, and encoder is not 'copy' or 'None'
            if self.audio_bitrate and selected_tracks and self.selected_audio_encoder not in ('copy', 'None'):
                # Pass the comma-separated bitrate values directly
                command.extend(['-B', self.audio_bitrate])

            # Add the Audio Encoder Option if specified and not 'None'
            if self.selected_audio_encoder and self.selected_audio_encoder != 'None':
                command.extend(['-E', self.selected_audio_encoder])

            # Print the constructed command to the console
            full_command = ' '.join([f'"{arg}"' if ' ' in arg else arg for arg in command])
            print(f"HandBrake Command:\n{full_command}\n")  # Print to console

            # Also emit the command to the GUI's progress area
            self.progress.emit(f"HandBrake Command:\n{full_command}\n")

            # Run HandBrakeCLI and capture output
            try:
                # Set process priority based on the selected option
                creationflags = 0
                command_prefix = []
                if sys.platform.startswith('win'):
                    if self.process_priority == 'Normal':
                        creationflags = subprocess.NORMAL_PRIORITY_CLASS
                    elif self.process_priority == 'Below Normal':
                        creationflags = subprocess.BELOW_NORMAL_PRIORITY_CLASS
                    elif self.process_priority == 'Low':
                        creationflags = subprocess.IDLE_PRIORITY_CLASS
                    else:
                        creationflags = 0  # Default
                else:
                    # For Unix-like systems, you can set nice values
                    if self.process_priority == 'Normal':
                        nice_value = 0
                    elif self.process_priority == 'Below Normal':
                        nice_value = 10
                    elif self.process_priority == 'Low':
                        nice_value = 19
                    else:
                        nice_value = 0  # Default
                    # Adjust the command to set nice value
                    command_prefix = ['nice', '-n', str(nice_value)]

                full_command_with_prefix = command_prefix + command

                process = subprocess.Popen(
                    full_command_with_prefix, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    encoding='utf-8',
                    errors='replace',
                    text=True,
                    creationflags=creationflags
                )

                for line in process.stdout:
                    if self.should_display_line(line):
                        self.handbrake_output.emit(line.strip())
                        # Parse progress from HandBrake output
                        self.parse_handbrake_output(line.strip())
                process.wait()
                if process.returncode != 0:
                    self.progress.emit(f"❌ HandBrakeCLI exited with an error while processing {file_name}.\n")
                    self.current_file_progress.emit(0)  # Optionally reset progress on error
                else:
                    # Set current file progress to 100%
                    self.current_file_progress.emit(100)
                    self.progress.emit(f"✅ Completed: {file_name}\n")

                    # Emit signal to handle source file deletion
                    self.delete_file_signal.emit(file_path, self.delete_source_files)

            except Exception as e:
                self.progress.emit(f"❌ Error encoding {file_name}: {e}\n")

            # Increment the processed files counter
            self.processed_files += 1
            self.update_overall_progress(self.processed_files, 0)  # Reset current file progress after completion

        self.overall_progress.emit(100)  # Ensure overall progress is 100% at the end
        self.finished.emit()

    def update_overall_progress(self, processed, current_file_progress):
        """
        Calculate and emit the overall progress.
        """
        overall = (processed + (current_file_progress / 100)) / self.total_files * 100
        self.overall_progress.emit(int(overall))

    def get_duration(self, file_path):
        # Use MediaInfo to get the duration in seconds
        try:
            output = subprocess.check_output(
                [self.mediainfo_exe, '--Output=JSON', file_path],
                encoding='utf-8',
                errors='replace',
                text=True
            )
            data = json.loads(output)
            general_track = next(track for track in data['media']['track'] if track['@type'] == 'General')
            duration_str = general_track.get('Duration')

            if duration_str is None:
                self.progress.emit(f"❌ Duration not found in MediaInfo output for {os.path.basename(file_path)}.\n")
                return None

            # Convert duration to float without dividing by 1000
            duration_seconds = float(duration_str)
            return duration_seconds
        except Exception as e:
            self.progress.emit(f"❌ Error getting duration: {e}\n")
            return None

    def get_audio_bitrate(self, file_path):
        # Use MediaInfo to get audio bitrate in kbps
        try:
            output = subprocess.check_output(
                [self.mediainfo_exe, '--Output=JSON', file_path],
                encoding='utf-8',
                errors='replace',
                text=True
            )
            data = json.loads(output)
            tracks = data.get('media', {}).get('track', [])
            audio_bitrate_total = 0
            audio_tracks = [track for track in tracks if track.get('@type') == 'Audio']
            for track in audio_tracks:
                bitrate_str = track.get('BitRate')
                if bitrate_str and str(bitrate_str).lower() != "n/a":
                    audio_bitrate_total += float(bitrate_str) / 1000  # Convert bps to kbps
            return int(audio_bitrate_total)
        except Exception as e:
            self.progress.emit(f"❌ Error getting audio bitrate: {e}\n")
            return None

    def calculate_video_bitrate(self, duration, target_size_mb, audio_bitrate_values):
        # Validate and convert target_size_mb
        try:
            target_size_mb = float(self.target_size_mb)
        except ValueError:
            self.progress.emit("❌ Invalid target size specified.\n")
            return None

        # Ensure duration is valid
        if duration is None or duration <= 0:
            self.progress.emit("❌ Invalid duration.\n")
            return None

        # Validate and convert audio_bitrate_values
        if audio_bitrate_values:
            try:
                # Sum all audio bitrates to get total audio bitrate
                total_audio_bitrate = sum([float(bitrate) for bitrate in audio_bitrate_values])
                audio_bitrate_bps = total_audio_bitrate * 1000  # Convert kbps to bps
            except ValueError:
                self.progress.emit("❌ Invalid audio bitrate values.\n")
                return None
        else:
            self.progress.emit("❌ Audio bitrate values are missing.\n")
            return None

        # Proceed with bitrate calculation
        target_size_bits = target_size_mb * 8 * 1024 * 1024  # Convert MB to bits
        total_bitrate_bps = target_size_bits / duration  # Total bitrate in bits per second
        video_bitrate_bps = total_bitrate_bps - audio_bitrate_bps  # Subtract audio bitrate from total
        video_bitrate_kbps = video_bitrate_bps / 1000  # Convert back to kbps

        return int(video_bitrate_kbps)

    def get_output_file_path(self, input_file_path):
        # Use the specified destination folder and original filename
        file_name = os.path.basename(input_file_path)
        output_file = os.path.join(self.destination_folder, file_name)
        return output_file

    def should_display_line(self, line):
        # Filter out lines you don't want to display, if any
        return True  # Display all lines

    def parse_handbrake_output(self, line):
        """
        Parse HandBrakeCLI output to extract progress percentage and update the current file progress bar.
        """
        match = re.search(r'(\d+\.\d+) %', line)
        if match:
            percentage = float(match.group(1))
            # Calculate overall progress based on the instance variable
            overall = (self.processed_files + (percentage / 100)) / self.total_files * 100
            self.overall_progress.emit(int(overall))
            self.current_file_progress.emit(int(percentage))
        else:
            # Handle integer percentages
            match = re.search(r'(\d+) %', line)
            if match:
                percentage = int(match.group(1))
                overall = (self.processed_files + (percentage / 100)) / self.total_files * 100
                self.overall_progress.emit(int(overall))
                self.current_file_progress.emit(int(percentage))

    def format_duration(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        else:
            return f"{minutes}m {secs}s"

    def estimate_rf_value(self, file_path, target_size_mb, audio_bitrate_values):
        try:
            # Get duration of the video
            duration = self.get_duration(file_path)
            if duration is None:
                self.progress.emit(f"❌ Error getting duration for {os.path.basename(file_path)} during estimation.\n")
                return None

            # Calculate start time and duration for the sample segment
            sample_percentage = 0.05  # 5% sample
            sample_duration = duration * sample_percentage
            sample_start = (duration - sample_duration) / 2  # Start from the middle

            # Prepare temporary file paths
            temp_sample_file = os.path.join(self.destination_folder, 'temp_sample.mkv')
            temp_encoded_sample = os.path.join(self.destination_folder, 'temp_encoded_sample.mkv')

            # Remove temp files if they exist
            if os.path.exists(temp_sample_file):
                os.remove(temp_sample_file)
            if os.path.exists(temp_encoded_sample):
                os.remove(temp_encoded_sample)

            # Use ffmpeg to extract the sample segment
            ffmpeg_cmd = [
                self.ffmpeg_exe,
                '-y',
                '-ss', str(sample_start),
                '-i', file_path,
                '-t', str(sample_duration),
                '-c', 'copy',
                temp_sample_file
            ]
            self.progress.emit("🔍 Extracting sample segment for estimation...")
            result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', errors='replace')
            if result.returncode != 0:
                self.progress.emit(f"❌ Error extracting sample segment: {result.stderr}\n")
                return None

            # Set acceptable size range (±5% of target size)
            acceptable_lower_size = target_size_mb * 0.95
            acceptable_upper_size = target_size_mb * 1.05

            # Initialize variables for the Bisection Method
            lower_rf = 18
            upper_rf = 40
            rf_value = (lower_rf + upper_rf) / 2
            max_iterations = 10
            iteration = 0

            while iteration < max_iterations:
                iteration += 1

                # Prepare HandBrakeCLI command to encode the sample segment
                command = [
                    self.handbrake_cli,
                    '-i', temp_sample_file,
                    '-o', temp_encoded_sample,
                    '-e', self.selected_encoder,
                    '-q', str(rf_value)
                ]

                # Add preset if specified
                if self.preset_file and self.preset_name:
                    command.extend([
                        '--preset-import-file', self.preset_file,
                        '-Z', self.preset_name,
                    ])
                else:
                    command.append('--all-subtitles')  # Include subtitles if not using a preset

                # Add audio encoder if specified and not 'None'
                if self.selected_audio_encoder and self.selected_audio_encoder != 'None':
                    command.extend(['-E', self.selected_audio_encoder])
                    # Include audio bitrate if specified
                    if self.audio_bitrate:
                        command.extend(['-B', self.audio_bitrate])

                # Run HandBrakeCLI on the sample
                self.progress.emit(f"🔄 Encoding sample segment for estimation (RF={rf_value:.2f})...")
                result = subprocess.run(
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    encoding='utf-8', errors='replace'
                )
                if result.returncode != 0:
                    self.progress.emit(f"❌ Error encoding sample segment: {result.stdout}\n")
                    return None

                # Check if temp_encoded_sample exists
                if not os.path.exists(temp_encoded_sample):
                    self.progress.emit(f"❌ temp_encoded_sample.mkv was not created. Possible encoding error.\n")
                    self.progress.emit(f"HandBrakeCLI output:\n{result.stdout}\n")
                    return None

                # Measure the size of the encoded sample
                sample_size_bytes = os.path.getsize(temp_encoded_sample)

                # Estimate the total size based on sample
                estimated_video_size_bytes = sample_size_bytes * (duration / sample_duration)

                # Calculate total estimated size including audio
                total_audio_bitrate_kbps = sum([float(bitrate) for bitrate in audio_bitrate_values])
                total_audio_size_bytes = (total_audio_bitrate_kbps * 1000 / 8) * duration  # Convert kbps to bytes per second

                estimated_total_size_bytes = estimated_video_size_bytes + total_audio_size_bytes
                estimated_total_size_mb = estimated_total_size_bytes / (1024 * 1024)

                self.progress.emit(f"📊 Estimated total size with RF={rf_value:.2f}: {estimated_total_size_mb:.2f} MB\n")

                # Check if the estimated size is within the acceptable range
                if acceptable_lower_size <= estimated_total_size_mb <= acceptable_upper_size:
                    # Within acceptable range
                    break

                # Adjust RF bounds based on estimated size
                if estimated_total_size_mb > acceptable_upper_size:
                    # Estimated size is too large; increase RF
                    lower_rf = rf_value
                else:
                    # Estimated size is too small; decrease RF
                    upper_rf = rf_value

                # Update RF value for next iteration
                rf_value = (lower_rf + upper_rf) / 2

                # Clean up temporary encoded sample
                os.remove(temp_encoded_sample)

            # Clean up temporary files
            os.remove(temp_sample_file)
            if os.path.exists(temp_encoded_sample):
                os.remove(temp_encoded_sample)

            # Return the estimated RF value
            return round(rf_value, 2)

        except Exception as e:
            self.progress.emit(f"❌ Error during estimation: {e}\n")
            return None

class AddMediaWorker(QThread):
    progress = pyqtSignal(list)  # Existing signal to emit media info
    log = pyqtSignal(str)        # New signal to emit log messages
    finished = pyqtSignal()

    def __init__(self, file_paths, mediainfo_exe):
        super().__init__()
        self.file_paths = file_paths
        self.mediainfo_exe = mediainfo_exe

    def get_full_language_name(self, language_str):
        """
        Converts language codes to their full language names using pycountry.
        If the language_str is already a full name or unknown, it returns it as is.
        """
        # Split multiple languages if present (e.g., 'en,fr')
        languages = [lang.strip() for lang in language_str.split(',')]
        full_languages = []
        for lang in languages:
            if not lang:
                continue  # Skip empty strings
            # Attempt to get the language by alpha_2 code
            language = pycountry.languages.get(alpha_2=lang.lower())
            if language:
                full_name = language.name
            else:
                # Attempt to get the language by alpha_3 code
                language = pycountry.languages.get(alpha_3=lang.lower())
                if language:
                    full_name = language.name
                else:
                    # Attempt to get the language by name
                    try:
                        language = pycountry.languages.lookup(lang)
                        full_name = language.name
                    except LookupError:
                        full_name = lang  # Fallback to original string if not found
            full_languages.append(full_name)
        # Join multiple languages back into a string
        return ', '.join(full_languages)

    def run(self):
        media_files = []
        for file_path in self.file_paths:
            if self.is_media_file(file_path):
                media_info = self.get_media_info(file_path)
                if media_info:
                    media_files.append(media_info)
                    self.progress.emit([media_info])  # Emit media info as soon as it's ready
        self.finished.emit()

    def is_media_file(self, file_path):
        return file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov'))

    def get_media_info(self, file_path):
        try:
            output = subprocess.check_output(
                [self.mediainfo_exe, '--Output=JSON', file_path],
                encoding='utf-8',
                errors='replace',
                text=True
            )
            data = json.loads(output)
            tracks = data.get('media', {}).get('track', [])

            # Initialize variables
            general_track = None
            video_track = None
            audio_tracks = []
            total_audio_bitrate_kbps = 0  # Initialize total audio bitrate

            for track in tracks:
                if track.get('@type') == 'General':
                    general_track = track
                elif track.get('@type') == 'Video' and not video_track:
                    video_track = track
                elif track.get('@type') == 'Audio':
                    audio_tracks.append(track)
                    # Accumulate audio bitrate
                    bitrate_str = track.get('BitRate')
                    if bitrate_str and str(bitrate_str).lower() != "n/a":
                        try:
                            total_audio_bitrate_kbps += float(bitrate_str) / 1000  # Convert bps to kbps
                        except ValueError:
                            pass  # Ignore invalid bitrate values

            if not general_track or not video_track or not audio_tracks:
                raise ValueError("Missing required track information.")

            file_size = os.path.getsize(file_path)

            # Define a function to format bitrate with '.' as thousands separator
            def format_bitrate_kbps(value):
                s = f"{value:,.0f}"  # Format with ',' as thousands separator
                return s.replace(',', '.')

            # Video bitrate formatting with enhanced handling
            video_info_list = []
            if video_track:
                # Collect video details
                video_codec = video_track.get('Format', 'Unknown')
                video_bitrate = video_track.get('BitRate')
                video_bitrate_formatted = "Unknown"
                if video_bitrate and str(video_bitrate).lower() != "n/a":
                    try:
                        video_bitrate_float = float(video_bitrate) / 1000  # Convert to kbps
                        video_bitrate_formatted = format_bitrate_kbps(video_bitrate_float)
                    except ValueError:
                        pass

                # Resolution
                width = video_track.get('Width', 'Unknown')
                height = video_track.get('Height', 'Unknown')
                resolution = f"{width}x{height}"

                # Frame rate
                frame_rate = video_track.get('FrameRate', 'Unknown')

                # Build video info list
                video_info_list.append(f"Codec: {video_codec}")
                video_info_list.append(f"Bitrate: {video_bitrate_formatted} kbps")
                video_info_list.append(f"Resolution: {resolution}")
                video_info_list.append(f"Frame Rate: {frame_rate} fps")

                # Combine into multi-line string
                video_info = "\n".join(video_info_list)
                # For display in the column, use a summary
                video_summary = f"{video_codec} {video_bitrate_formatted} kbps"
            else:
                video_info = "Unknown"
                video_summary = "Unknown"

            # Audio bitrate and language formatting
            audio_info_list = []
            for idx, audio_track in enumerate(audio_tracks, start=1):
                bitrate_str = audio_track.get('BitRate')
                language_str = audio_track.get('Language/String') or audio_track.get('Language') or "Unknown"
                # Convert language codes to full names using the shared function
                full_language = get_full_language_name(language_str)
                if isinstance(full_language, list):
                    full_language = ', '.join(full_language)
                if bitrate_str and isinstance(bitrate_str, (int, float, str)) and str(bitrate_str).lower() != "n/a":
                    try:
                        bitrate_float = float(bitrate_str) / 1000  # Convert to kbps
                        audio_codec = audio_track.get('Format', 'Unknown')
                        bitrate_display = f"{int(bitrate_float)} kbps" if bitrate_float else "Unknown Bitrate"
                    except ValueError:
                        bitrate_display = "Unknown Bitrate"
                else:
                    bitrate_display = "Unknown Bitrate"

                # Retrieve the Title if available
                title = audio_track.get('Title', '').strip()

                if title:
                    # Include the Title in the display if it exists
                    audio_info = f"{idx}: {title} - {audio_track.get('Format', 'Unknown')} {bitrate_display} [{full_language}]"
                else:
                    # Fallback to original format if Title is not available
                    audio_info = f"{idx}: {audio_track.get('Format', 'Unknown')} {bitrate_display} [{full_language}]"

                audio_info_list.append(audio_info)

            audio_info = "\n".join(audio_info_list)

            # Get duration and format it
            duration_str = general_track.get('Duration')
            if duration_str is None or str(duration_str).lower() == "n/a":
                duration_formatted = "Unknown"
                duration_seconds = None
            else:
                try:
                    duration_seconds = float(duration_str)
                    duration_formatted = self.format_duration(duration_seconds)
                except ValueError:
                    duration_formatted = "Unknown"
                    duration_seconds = None

            # Return info as a dict
            info = {
                'filename': os.path.basename(file_path),
                'duration': duration_formatted,
                'duration_seconds': duration_seconds,
                'video': video_summary,      # Display summary in the column
                'video_info': video_info,    # Store detailed info for tooltip
                'audio': audio_info,
                'size': f"{int(file_size / (1024 * 1024))} MB",
                'size_bytes': file_size,
                'total_audio_bitrate_kbps': total_audio_bitrate_kbps,  # Store total audio bitrate
                'path': file_path,
                'audio_tracks': audio_tracks  # Store all audio tracks for selection
            }
            return info
        except Exception as e:
            self.update_progress(f"Error getting media info for {file_path}: {e}")
            return None

    def format_duration(self, duration_seconds):
        """
        Formats duration from seconds to HH:MM:SS format.
        """
        try:
            hours = int(duration_seconds // 3600)
            minutes = int((duration_seconds % 3600) // 60)
            seconds = int(duration_seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except:
            return "Unknown"

class MediaListWidget(QTreeWidget):
    deletePressed = pyqtSignal()  # Signal for delete key functionality
    audioSelectionRequested = pyqtSignal(list)  # Signal to request audio track selection

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_context_menu)

        # Initialize custom tooltip widget for Audio column
        self.audio_tooltip = QLabel(self)
        self.audio_tooltip.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.audio_tooltip.setStyleSheet("""
            QLabel {
                background-color: #FFFFFF;  /* White Background */
                color: #000000;             /* Black Text */
                border: 1px solid #A0A0A0;  /* Gray Border */
                padding: 5px;
                font-size: 9pt;             /* Increased Font Size */
            }
        """)
        self.audio_tooltip.setVisible(False)

        # Initialize custom tooltip widget for Video column
        self.video_tooltip = QLabel(self)
        self.video_tooltip.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.video_tooltip.setStyleSheet("""
            QLabel {
                background-color: #FFFFFF;  /* White Background */
                color: #000000;             /* Black Text */
                border: 1px solid #A0A0A0;  /* Gray Border */
                padding: 5px;
                font-size: 9pt;             /* Increased Font Size */
            }
        """)
        self.video_tooltip.setVisible(False)

        # Initialize hover timers for delayed tooltip display
        self.hover_timer_audio = QTimer(self)
        self.hover_timer_audio.setSingleShot(True)
        self.hover_timer_audio.timeout.connect(self.show_audio_tooltip)

        self.hover_timer_video = QTimer(self)
        self.hover_timer_video.setSingleShot(True)
        self.hover_timer_video.timeout.connect(self.show_video_tooltip)

        # Variables to track the current hovered item and column for Audio
        self.current_hover_item_audio = None
        self.current_hover_column_audio = -1
        self.last_hover_pos_audio = QPoint()

        # Variables to track the current hovered item and column for Video
        self.current_hover_item_video = None
        self.current_hover_column_video = -1
        self.last_hover_pos_video = QPoint()

        # Enable mouse tracking to receive mouseMoveEvent without mouse buttons pressed
        self.setMouseTracking(True)

        # Connect the selectionChanged signal to ensure at least one item is always selected
        self.selectionModel().selectionChanged.connect(self.on_selection_changed)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.deletePressed.emit()  # Emit the signal when Delete key is pressed
        else:
            super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.pos()
        item = self.itemAt(pos)
        column = self.columnAt(pos.x())

        if item and column == COL_AUDIO:
            if (item != self.current_hover_item_audio) or (column != self.current_hover_column_audio):
                # Mouse has moved to a different item or column
                self.hover_timer_audio.stop()
                self.current_hover_item_audio = item
                self.current_hover_column_audio = column
                self.last_hover_pos_audio = self.viewport().mapToGlobal(pos)
                self.hover_timer_audio.start(1000)  # Start 1-second timer for tooltip
                self.audio_tooltip.setVisible(False)  # Hide tooltip until timer triggers
                self.video_tooltip.setVisible(False)  # Hide video tooltip
                self.hover_timer_video.stop()  # Stop video timer if running
        elif item and column == COL_VIDEO:
            if (item != self.current_hover_item_video) or (column != self.current_hover_column_video):
                # Mouse has moved to a different item or column
                self.hover_timer_video.stop()
                self.current_hover_item_video = item
                self.current_hover_column_video = column
                self.last_hover_pos_video = self.viewport().mapToGlobal(pos)
                self.hover_timer_video.start(1000)  # Start 1-second timer for tooltip
                self.video_tooltip.setVisible(False)  # Hide tooltip until timer triggers
                self.audio_tooltip.setVisible(False)  # Hide audio tooltip
                self.hover_timer_audio.stop()  # Stop audio timer if running
        else:
            # Mouse is not over the Audio or Video column
            self.hover_timer_audio.stop()
            self.current_hover_item_audio = None
            self.current_hover_column_audio = -1
            self.audio_tooltip.setVisible(False)  # Hide audio tooltip

            self.hover_timer_video.stop()
            self.current_hover_item_video = None
            self.current_hover_column_video = -1
            self.video_tooltip.setVisible(False)  # Hide video tooltip

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        # Hide tooltips when the mouse leaves the widget
        self.hover_timer_audio.stop()
        self.current_hover_item_audio = None
        self.current_hover_column_audio = -1
        self.audio_tooltip.setVisible(False)

        self.hover_timer_video.stop()
        self.current_hover_item_video = None
        self.current_hover_column_video = -1
        self.video_tooltip.setVisible(False)
        super().leaveEvent(event)

    def show_audio_tooltip(self):
        """
        Displays the custom tooltip near the mouse cursor with audio information.
        """
        if self.current_hover_item_audio and self.current_hover_column_audio == COL_AUDIO:
            audio_text = self.current_hover_item_audio.text(COL_AUDIO)
            if audio_text:
                self.audio_tooltip.setText(audio_text)
                self.audio_tooltip.adjustSize()
                # Position the tooltip slightly offset from the cursor
                tooltip_x = self.last_hover_pos_audio.x() + 8
                tooltip_y = self.last_hover_pos_audio.y() + 8
                self.audio_tooltip.move(tooltip_x, tooltip_y)
                self.audio_tooltip.setVisible(True)

    def show_video_tooltip(self):
        """
        Displays the custom tooltip near the mouse cursor with video information.
        """
        if self.current_hover_item_video and self.current_hover_column_video == COL_VIDEO:
            # Get the detailed video info from media_dict
            media_dict = self.current_hover_item_video.media_dict
            if media_dict:
                video_info = media_dict['info'].get('video_info', '')
                if video_info:
                    self.video_tooltip.setText(video_info)
                    self.video_tooltip.adjustSize()
                    # Position the tooltip slightly offset from the cursor
                    tooltip_x = self.last_hover_pos_video.x() + 8
                    tooltip_y = self.last_hover_pos_video.y() + 8
                    self.video_tooltip.move(tooltip_x, tooltip_y)
                    self.video_tooltip.setVisible(True)

    def open_context_menu(self, position):
        # Create a context menu
        menu = QMenu(self)

        # Add only the "Select Audio Tracks" action to the context menu
        select_audio_action = QAction("Select Audio Tracks", self)
        menu.addAction(select_audio_action)

        # Connect the "Select Audio Tracks" action to its respective method
        select_audio_action.triggered.connect(self.handle_select_audio_tracks)

        # Display the context menu at the cursor position
        menu.exec_(QCursor.pos())

    def handle_select_audio_tracks(self):
        # Emit a signal with the selected items for audio track selection
        selected_items = self.selectedItems()
        self.audioSelectionRequested.emit(selected_items)

    def on_selection_changed(self, selected, deselected):
        """
        Ensures that at least one media item is always selected.
        If no items are selected, it reselects the first item.
        """
        if not self.selectedItems():
            if self.topLevelItemCount() > 0:
                self.setCurrentItem(self.topLevelItem(0))

class AudioSelectionDialog(QDialog):
    def __init__(self, audio_tracks_or_labels, parent=None):
        super().__init__(parent)
        
        # Remove the "?" Help Button
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        self.setWindowTitle("Select Audio Tracks to Encode")
        self.setModal(True)
        self.resize(500, 300)

        self.selected_tracks = []

        layout = QVBoxLayout()

        self.list_widget = QListWidget()

        if isinstance(audio_tracks_or_labels[0], dict):
            # It's a list of audio_tracks dictionaries (single file)
            for idx, track in enumerate(audio_tracks_or_labels, start=1):
                # Handle Bitrate
                bitrate = track.get('BitRate')
                if bitrate and isinstance(bitrate, (int, float, str)) and str(bitrate).lower() != "n/a":
                    try:
                        bitrate_float = float(bitrate)
                        bitrate_display = f"{int(bitrate_float / 1000)} kbps"
                    except ValueError:
                        bitrate_display = "Unknown Bitrate"
                else:
                    bitrate_display = "Unknown Bitrate"

                # Retrieve and convert the Language using the shared function
                language_str = track.get('Language/String') or track.get('Language') or "Unknown"
                full_language = get_full_language_name(language_str)

                # Retrieve the Title if available
                title = track.get('Title', '').strip()

                if title:
                    # Include the Title in the display if it exists
                    item_text = f"{idx}: {title} - {track.get('Format', 'Unknown')} {bitrate_display} [{full_language}]"
                else:
                    # Fallback to original format if Title is not available
                    item_text = f"{idx}: {track.get('Format', 'Unknown')} {bitrate_display} [{full_language}]"

                item = QListWidgetItem(item_text)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                self.list_widget.addItem(item)
        else:
            # It's a list of track labels (multiple files)
            for idx, label in enumerate(audio_tracks_or_labels, start=1):
                item = QListWidgetItem(label)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def get_selected_tracks(self):
        selected = []
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.checkState() == Qt.Checked:
                selected.append(index)
        return selected

class QPushButtonWithToolTip(QPushButton):
    def event(self, e):
        if e.type() == QEvent.ToolTip:
            # Show the tooltip even if the button is disabled
            if self.toolTip():
                QToolTip.showText(e.globalPos(), self.toolTip(), self)
            return True
        return super().event(e)

class MediaEncoderGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.media_files = []  # List to store media file paths and info
        self.target_size_mb = None
        self.audio_bitrate = None
        self.destination_folder = None
        self.selected_encoder = None  # Initialize selected encoder
        self.selected_audio_encoder = 'av_aac'  # Initialize with default value
        self.selected_priority = 'Normal'  # Initialize selected process priority
        
        self.encoding_in_progress = False  # Add this line

        # Get script directory and set up dependencies path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dependencies_dir = os.path.join(script_dir, '__dependencies__')
        self.dependencies_dir = dependencies_dir  # Store for later use

        # Paths to your executables
        self.handbrake_cli = os.path.join(dependencies_dir, 'HandBrakeCLI.exe')
        self.mediainfo_exe = os.path.join(dependencies_dir, 'MediaInfo.exe')
        self.mkvpropedit_exe = os.path.join(dependencies_dir, 'mkvpropedit.exe')
        self.ffmpeg_exe = os.path.join(dependencies_dir, 'ffmpeg.exe')  # Add this line

        # Define the icon path
        self.icon_path = os.path.join(dependencies_dir, 'favicon.ico')
        if not os.path.exists(self.icon_path):
            self.icon_path = None  # Optionally set to a default icon path

        # Load preset files from __presets__ directory
        self.presets_dir = os.path.join(dependencies_dir, '__presets__')  # Modified this line
        self.preset_files = self.load_preset_files(self.presets_dir)       # Modified this line

        # Initialize worker threads
        self.check_media_worker = None
        self.encoding_worker = None
        self.add_media_worker = None

        # Initialize database
        self.db_path = os.path.join(self.dependencies_dir, 'settings.db')
        self.init_db()

        # Initialize UI after setting up dependencies and database
        self.initUI()

        # Load settings
        self.load_settings()

    def update_info_panel(self):
        """
        Update the calculated bitrate and estimated space saved in the info panel.
        """
        # Get selected items
        selected_items = self.media_list.selectedItems()

        # If no files are selected, show N/A for both fields and return early
        if not selected_items:
            self.calculated_bitrate_label.setText("Calculated Video Bitrate: N/A")
            self.space_saved_label.setText("Estimated Space Saved: N/A")
            return

        # First, validate inputs
        try:
            target_size_mb = float(self.target_size_input.text())
        except ValueError:
            self.calculated_bitrate_label.setText("Calculated Video Bitrate: N/A")
            self.space_saved_label.setText("Estimated Space Saved: N/A")
            return

        # Use only the selected files for calculations
        media_files_to_use = [item.media_dict for item in selected_items]

        # Reset cumulative values for accurate calculations
        total_duration = 0  # in seconds
        total_input_size = 0  # in bytes
        total_audio_bitrate_bps = 0  # in bits per second
        total_video_bitrate_bps = 0  # in bits per second

        selected_audio_encoder = self.audio_encoder_combo.currentText()

        for media in media_files_to_use:
            # Get media info
            media_info = media.get('info')

            # Ensure media info is valid
            if not media_info:
                continue

            # Get file size in bytes
            size_bytes = media_info.get('size_bytes', 0)
            total_input_size += size_bytes

            # Get duration in seconds
            duration_seconds = media_info.get('duration_seconds')
            if duration_seconds is None:
                self.calculated_bitrate_label.setText("Calculated Video Bitrate: N/A")
                self.space_saved_label.setText("Estimated Space Saved: N/A")
                return
            total_duration += duration_seconds

            # Handle audio bitrate
            if selected_audio_encoder in ('copy', 'None'):
                # Use the stored total audio bitrate from media_info if 'copy' or 'None'
                media_audio_bitrate_kbps = media_info.get('total_audio_bitrate_kbps', 0)
                total_audio_bitrate_bps += media_audio_bitrate_kbps * 1000  # Convert to bits per second
            else:
                # Calculate based on selected audio tracks
                selected_audio_tracks = media.get('selected_audio_tracks', [])
                if self.audio_bitrate_input.text():
                    bitrate_values = [bitrate.strip() for bitrate in self.audio_bitrate_input.text().split(',')]
                    # Sum bitrate for selected tracks
                    if len(bitrate_values) == len(selected_audio_tracks):
                        try:
                            # Accumulate total audio bitrate for the selected tracks
                            total_audio_bitrate_kbps = sum(float(bitrate_values[i]) for i in range(len(selected_audio_tracks)))
                            total_audio_bitrate_bps += total_audio_bitrate_kbps * 1000  # Convert kbps to bps
                        except ValueError:
                            self.calculated_bitrate_label.setText("Calculated Video Bitrate: N/A")
                            self.space_saved_label.setText("Estimated Space Saved: N/A")
                            return

        if total_duration <= 0:
            self.calculated_bitrate_label.setText("Calculated Video Bitrate: N/A")
            self.space_saved_label.setText("Estimated Space Saved: N/A")
            return

        # Calculate total target size in bits (for all selected files)
        total_target_size_bits = target_size_mb * 8 * 1024 * 1024 * len(media_files_to_use)

        # Total bitrate for all files (audio + video)
        total_bitrate_bps = total_target_size_bits / total_duration

        # Subtract total audio bitrate from total bitrate to get the video bitrate
        total_video_bitrate_bps = total_bitrate_bps - total_audio_bitrate_bps

        if total_video_bitrate_bps < 0:
            # If the audio bitrate is too large and results in a negative value, handle it by setting N/A
            self.calculated_bitrate_label.setText("Calculated Video Bitrate: N/A")
        else:
            # Convert to kbps and update UI
            video_bitrate_kbps = total_video_bitrate_bps / 1000  # Convert back to kbps
            self.calculated_bitrate_label.setText(f"Calculated Video Bitrate: {int(video_bitrate_kbps)} kbps")

        # Calculate estimated space saved
        total_input_size_mb = total_input_size / (1024 * 1024)
        space_saved_mb = total_input_size_mb - target_size_mb * len(media_files_to_use)
        if total_input_size_mb > 0:
            percentage_saved = (space_saved_mb / total_input_size_mb) * 100
            self.space_saved_label.setText(f"Estimated Space Saved: {percentage_saved:.1f}%")
        else:
            self.space_saved_label.setText("Estimated Space Saved: N/A")

    def get_audio_bitrate(self, file_path):
        # Use MediaInfo to get audio bitrate in kbps
        try:
            output = subprocess.check_output(
                [self.mediainfo_exe, '--Output=JSON', file_path],
                encoding='utf-8',
                errors='replace',
                text=True
            )
            data = json.loads(output)
            tracks = data.get('media', {}).get('track', [])
            audio_bitrate_total = 0
            audio_tracks = [track for track in tracks if track.get('@type') == 'Audio']
            for track in audio_tracks:
                bitrate_str = track.get('BitRate')
                if bitrate_str and str(bitrate_str).lower() != "n/a":
                    audio_bitrate_total += float(bitrate_str) / 1000  # Convert bps to kbps
            return int(audio_bitrate_total)
        except Exception as e:
            print(f"Error getting audio bitrate: {e}")
            return None

    def load_preset_files(self, folder_path):
        preset_files = {}
        for file_name in os.listdir(folder_path):
            if file_name.endswith('.json'):
                preset_name = os.path.splitext(file_name)[0]
                preset_path = os.path.join(folder_path, file_name)
                preset_files[preset_name] = preset_path
        return preset_files

    def init_db(self):
        # Initialize the database and create tables if not exists
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS column_widths (
                column_index INTEGER PRIMARY KEY,
                width INTEGER
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        self.conn.commit()

    def save_setting(self, key, value):
        # Save a setting to the database
        self.cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
        ''', (key, value))
        self.conn.commit()

    def load_setting(self, key, default=None):
        # Load a setting from the database
        self.cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        result = self.cursor.fetchone()
        return result[0] if result else default

    def save_column_width(self, column_index, width):
        # Save the width of a column to the database
        self.cursor.execute('''
            INSERT OR REPLACE INTO column_widths (column_index, width)
            VALUES (?, ?)
        ''', (column_index, width))
        self.conn.commit()

    def load_column_widths(self):
        # Load column widths from the database
        self.cursor.execute('SELECT column_index, width FROM column_widths')
        rows = self.cursor.fetchall()
        widths = {col_index: width for col_index, width in rows}
        # Set column widths
        for col_index in [COL_FILENAME, COL_DURATION, COL_VIDEO, COL_AUDIO, COL_SIZE]:
            width = widths.get(col_index, DEFAULT_COL_WIDTHS[col_index])
            self.media_list.setColumnWidth(col_index, width)

    def create_headline(self, headline_config):
        """
        Create a styled QLabel based on the provided configuration.

        Parameters:
            headline_config (dict): A dictionary containing 'text', 'font_size',
                                    'bold', and 'color' keys.

        Returns:
            QLabel: A styled QLabel widget.
        """
        font = QFont()
        font.setPointSizeF(headline_config.get('font_size', 12))
        font.setBold(headline_config.get('bold', True))
        label = QLabel(headline_config.get('text', ''))
        label.setFont(font)
        label.setStyleSheet(f"color: {headline_config.get('color', '#000000')};")
        return label

    def initUI(self):
        # Set window properties
        self.setWindowTitle('HandBrake: Target Size Bulk Encoder')
        if self.icon_path and os.path.exists(self.icon_path):
            self.setWindowIcon(QIcon(self.icon_path))  # Set the window icon
        self.setAcceptDrops(True)  # Enable drag-and-drop

        # Only set the default size if window size was not loaded
        if not getattr(self, 'window_size_loaded', False):
            self.resize(MEDIA_LIST_WIDTH, MEDIA_LIST_HEIGHT + PROGRESS_AREA_HEIGHT + OUTPUT_AREA_HEIGHT + 300)

        # Main Layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)  # Set uniform spacing between sections

        ##### 1. Destination Directory Section #####
        dest_section = QVBoxLayout()

        # Headline for Destination Directory
        dest_headline = self.create_headline(DEST_DIR_HEADLINE)
        dest_section.addWidget(dest_headline)

        # Destination Folder Layout
        dest_layout = QHBoxLayout()
        self.dest_input = QLineEdit()
        self.dest_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        dest_input_font = self.dest_input.font()
        dest_input_font.setPointSizeF(FONT_SIZE_DEST_INPUT)
        self.dest_input.setFont(dest_input_font)
        self.dest_browse_btn = QPushButton('Browse...')
        self.dest_browse_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        dest_layout.addWidget(self.dest_input)
        dest_layout.addWidget(self.dest_browse_btn)
        dest_section.addLayout(dest_layout)

        main_layout.addLayout(dest_section)

        ##### 2. Media List Section #####
        media_section = QVBoxLayout()
        media_section.setContentsMargins(0, 0, 0, 0)  # Adjust margins for better resizing

        # Headline for Media List
        media_headline = self.create_headline(MEDIA_LIST_HEADLINE)
        media_section.addWidget(media_headline)

        # Media List
        self.media_list = MediaListWidget()
        media_list_font = self.media_list.font()
        media_list_font.setPointSizeF(FONT_SIZE_MEDIA_LIST)
        self.media_list.setFont(media_list_font)
        self.media_list.setHeaderLabels(["Filename", "Duration", "Video", "Audio", "Size"])
        self.media_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Remove indentation to align filename to the left
        self.media_list.setIndentation(0)
        self.media_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # Enable sorting and set default sort
        self.media_list.setSortingEnabled(True)
        self.media_list.sortItems(COL_FILENAME, Qt.AscendingOrder)

        media_section.addWidget(self.media_list)

        ##### 3. Settings Layout #####
        settings_layout = QGridLayout()

        # Target Size
        target_size_label = QLabel('Target Size (MB):')

        # Create an inner layout for the input and checkboxes
        target_size_layout = QHBoxLayout()
        self.target_size_input = QLineEdit()
        self.target_size_input.setFixedWidth(100)
        self.target_size_input.setToolTip("Enter the desired target size for the encoded video in megabytes (MB).")
        self.variable_bitrate_checkbox = QCheckBox('Constant Quality')
        self.variable_bitrate_checkbox.setToolTip("Set the desired quality factor.")
        self.variable_bitrate_checkbox.setChecked(False)  # By default unchecked

        target_size_layout.addWidget(self.target_size_input)

        # Add horizontal spacer
        target_size_layout.addSpacerItem(QSpacerItem(10, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))

        # Add the Constant Quality checkbox to the layout
        target_size_layout.addWidget(self.variable_bitrate_checkbox)

        settings_layout.addWidget(target_size_label, 0, 0, alignment=Qt.AlignRight)
        settings_layout.addLayout(target_size_layout, 0, 1)

        # Now, create the Multi-Pass checkbox
        self.multi_pass_checkbox = QCheckBox('Multi-Pass')
        self.multi_pass_checkbox.setToolTip("Enable or disable multi-pass encoding.")
        self.multi_pass_checkbox.setChecked(False)  # Default to unchecked at GUI start

        # Audio Bitrate
        audio_bitrate_label = QLabel('Audio Bitrate (kbps):')

        # Create an inner layout for the input and checkboxes
        audio_bitrate_layout = QHBoxLayout()
        self.audio_bitrate_input = QLineEdit()
        self.audio_bitrate_input.setFixedWidth(100)
        self.audio_bitrate_input.setToolTip(
            "Specify the audio bitrate in kbps. For multiple audio tracks, enter comma-separated values (e.g., '320,192')."
        )

        # Add the audio bitrate input to the layout
        audio_bitrate_layout.addWidget(self.audio_bitrate_input)

        # Add horizontal spacer
        audio_bitrate_layout.addSpacerItem(QSpacerItem(10, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))

        # Add the Multi-Pass checkbox to the layout
        audio_bitrate_layout.addWidget(self.multi_pass_checkbox)

        # Now add the label and the layout to settings_layout
        settings_layout.addWidget(audio_bitrate_label, 1, 0, alignment=Qt.AlignRight)
        settings_layout.addLayout(audio_bitrate_layout, 1, 1)

        # Info Panel
        info_panel_layout = QVBoxLayout()
        self.calculated_bitrate_label = QLabel("Calculated Video Bitrate: N/A")
        self.space_saved_label = QLabel("Estimated Space Saved: N/A")
        info_panel_layout.addWidget(self.calculated_bitrate_label)
        info_panel_layout.addWidget(self.space_saved_label)
        info_panel_layout.setAlignment(Qt.AlignCenter)  # Center the info panel

        # Set Font Size for Info Panel Labels
        info_panel_font = QFont()
        info_panel_font.setPointSizeF(FONT_SIZE_INFO_PANEL)  # Changed to setPointSizeF
        self.calculated_bitrate_label.setFont(info_panel_font)
        self.space_saved_label.setFont(info_panel_font)

        info_panel_widget = QWidget()
        info_panel_widget.setLayout(info_panel_layout)
        settings_layout.addWidget(info_panel_widget, 0, 2, 2, 1)  # Spanning 2 rows

        # Preset selection
        preset_label = QLabel('Select Preset:')
        settings_layout.addWidget(preset_label, 0, 3, alignment=Qt.AlignRight)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem('None')  # Add 'None' option at the top
        self.preset_combo.addItems(sorted(self.preset_files.keys()))
        # Set tooltip to inform about 'None' option
        self.preset_combo.setToolTip(
            "Select a preset for encoding. Choose 'None' to proceed without a preset."
        )
        # Set width, height, and font size for the preset combo box
        self.preset_combo.setFixedWidth(COMBO_BOX_WIDTH)
        self.preset_combo.setFixedHeight(COMBO_BOX_HEIGHT)
        combo_box_font = self.preset_combo.font()
        combo_box_font.setPointSizeF(FONT_SIZE_COMBO_BOX)
        self.preset_combo.setFont(combo_box_font)
        settings_layout.addWidget(self.preset_combo, 0, 4)

        # Adjust column stretch
        settings_layout.setColumnStretch(2, 1)  # Allow the info panel to expand
        settings_layout.setColumnStretch(0, 0)
        settings_layout.setColumnStretch(1, 0)
        settings_layout.setColumnStretch(3, 0)
        settings_layout.setColumnStretch(4, 0)

        # Optionally, adjust spacing
        settings_layout.setHorizontalSpacing(10)
        settings_layout.setVerticalSpacing(5)

        ##### 4. Buttons Layout #####
        buttons_layout = QHBoxLayout()
        self.check_media_btn = QPushButton('Check Media')
        self.start_encoding_btn = QPushButtonWithToolTip('Start Encoding')  # Use the subclass here
        self.start_encoding_btn.setEnabled(False)  # Disabled until settings are set
        self.clear_media_btn = QPushButton('Clear Media')
        buttons_layout.addWidget(self.check_media_btn)
        buttons_layout.addWidget(self.start_encoding_btn)
        buttons_layout.addWidget(self.clear_media_btn)

        ##### Add settings and buttons to media section #####
        media_section.addLayout(settings_layout)
        media_section.addLayout(buttons_layout)

        ##### Add the combo boxes under the buttons aligned to the left #####
        checkbox_layout = QHBoxLayout()

        # Left side (combo boxes)
        left_combo_layout = QHBoxLayout()

        # Delete Source option
        delete_source_label = QLabel("Delete Source:")
        self.delete_source_combo = QComboBox()
        delete_source_options = ['Auto', 'Ask', 'No']
        self.delete_source_combo.addItems(delete_source_options)
        self.delete_source_combo.setToolTip(
            "Select 'auto' to automatically delete source files after successful encoding, "
            "'ask' to prompt for confirmation, or 'no' to keep source files."
        )
        # Set font size and dimensions for the delete source combo box
        combo_box_font = self.delete_source_combo.font()
        combo_box_font.setPointSizeF(FONT_SIZE_COMBO_BOX)
        self.delete_source_combo.setFont(combo_box_font)
        self.delete_source_combo.setFixedWidth(COMBO_BOX_WIDTH)
        self.delete_source_combo.setFixedHeight(COMBO_BOX_HEIGHT)
        left_combo_layout.addWidget(delete_source_label)
        left_combo_layout.addWidget(self.delete_source_combo)

        # Process Priority selection
        priority_label = QLabel("Process Priority:")
        self.priority_combo = QComboBox()
        # Add process priority options
        priority_options = [
            'Normal',
            'Below Normal',
            'Low'
        ]
        self.priority_combo.addItems(priority_options)
        # Set default value
        self.priority_combo.setCurrentText('Normal')
        self.priority_combo.setToolTip(
            "Set the process priority for encoding. 'Normal' is default, 'Below Normal' and 'Low' decrease the priority."
        )
        # Set font size and dimensions for the priority combo box
        self.priority_combo.setFont(combo_box_font)
        self.priority_combo.setFixedWidth(COMBO_BOX_WIDTH)
        self.priority_combo.setFixedHeight(COMBO_BOX_HEIGHT)
        left_combo_layout.addWidget(priority_label)
        left_combo_layout.addWidget(self.priority_combo)

        # Add left_combo_layout to the checkbox_layout
        checkbox_layout.addLayout(left_combo_layout)
        checkbox_layout.addStretch()  # Add stretch to push the next widgets to the right

        # Right side layout (Encoder Selection)
        right_encoder_layout = QHBoxLayout()

        # Video Encoder selection
        encoder_label = QLabel("Video:")
        right_encoder_layout.addWidget(encoder_label)

        self.encoder_combo = QComboBox()
        # Add the encoder options to the combo box
        self.encoder_options = [
            'svt_av1',
            'svt_av1_10bit',
            'x264',
            'x264_10bit',
            'nvenc_h264',
            'x265',
            'x265_10bit',
            'x265_12bit',
            'nvenc_h265',
            'nvenc_h265_10bit',
            'mpeg4',
            'mpeg2',
            'VP8',
            'VP9',
            'VP9_10bit',
            'theora'
        ]
        self.encoder_combo.addItems(self.encoder_options)
        # Set default value
        self.encoder_combo.setCurrentText('x265')

        # Set font size and dimensions for the encoder combo box
        encoder_combo_box_font = self.encoder_combo.font()
        encoder_combo_box_font.setPointSizeF(FONT_SIZE_COMBO_BOX)
        self.encoder_combo.setFont(encoder_combo_box_font)
        self.encoder_combo.setFixedWidth(COMBO_BOX_WIDTH)
        self.encoder_combo.setFixedHeight(COMBO_BOX_HEIGHT)

        right_encoder_layout.addWidget(self.encoder_combo)

        # Audio Encoder selection
        audio_encoder_label = QLabel("Audio:")
        right_encoder_layout.addWidget(audio_encoder_label)

        self.audio_encoder_combo = QComboBox()

        # Define AUDIO_ENCODER_OPTIONS Locally
        self.audio_encoder_options = [
            'av_aac',
            'ac3',
            'eac3',
            'mp3',
            'vorbis',
            'flac16',
            'flac24',
            'opus',
            'copy'
        ]

        self.audio_encoder_combo.addItems(self.audio_encoder_options)
        # Set default value
        self.audio_encoder_combo.setCurrentText('av_aac')

        # Set font size and dimensions for the audio encoder combo box
        audio_combo_box_font = self.audio_encoder_combo.font()
        audio_combo_box_font.setPointSizeF(FONT_SIZE_COMBO_BOX)
        self.audio_encoder_combo.setFont(audio_combo_box_font)
        self.audio_encoder_combo.setFixedWidth(COMBO_BOX_WIDTH)
        self.audio_encoder_combo.setFixedHeight(COMBO_BOX_HEIGHT)

        right_encoder_layout.addWidget(self.audio_encoder_combo)

        # Add right_encoder_layout to the checkbox_layout
        checkbox_layout.addLayout(right_encoder_layout)

        # Add the complete checkbox_layout to the media_section
        media_section.addLayout(checkbox_layout)

        ##### 5. Progress Area Section #####
        progress_section = QVBoxLayout()
        progress_section.setContentsMargins(0, 0, 0, 0)  # Adjust margins for better resizing
        progress_section.setSpacing(5)

        # Headline for Encoding Progress
        progress_headline = self.create_headline(ENCODING_PROGRESS_HEADLINE)
        progress_section.addWidget(progress_headline)

        # Progress Area
        self.progress_area = QTextEdit()
        progress_area_font = self.progress_area.font()
        progress_area_font.setPointSizeF(FONT_SIZE_PROGRESS_AREA)
        self.progress_area.setFont(progress_area_font)
        self.progress_area.setReadOnly(True)
        self.progress_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        progress_section.addWidget(self.progress_area)

        ##### 6. Output Area Section #####
        output_section = QVBoxLayout()
        output_section.setContentsMargins(0, 0, 0, 0)  # Adjust margins for better resizing
        output_section.setSpacing(5)

        # Headline for HandBrake Output
        output_headline = self.create_headline(HANDBRAKE_OUTPUT_HEADLINE)
        output_section.addWidget(output_headline)

        # Output Area (HandBrakeCLI Output)
        self.output_area = QTextEdit()
        output_area_font = self.output_area.font()
        output_area_font.setPointSizeF(FONT_SIZE_OUTPUT_AREA)
        self.output_area.setFont(output_area_font)
        self.output_area.setReadOnly(True)
        self.output_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        output_section.addWidget(self.output_area)

        # Add Current File Label and Progress Bars under the output area
        progress_info_layout = QVBoxLayout()

        # Current File Label
        self.current_file_label = QLabel("Current File: None")
        current_file_font = self.current_file_label.font()
        current_file_font.setPointSizeF(FONT_SIZE_LABELS)
        self.current_file_label.setFont(current_file_font)
        self.current_file_label.setStyleSheet("color: #000000;")
        self.current_file_label.setVisible(False)
        progress_info_layout.addWidget(self.current_file_label)

        # Create a horizontal layout for the progress bars
        progress_bars_layout = QHBoxLayout()

        # Overall Progress Bar
        self.overall_progress_bar = QProgressBar()
        self.overall_progress_bar.setMaximum(100)
        self.overall_progress_bar.setValue(0)
        self.overall_progress_bar.setFormat('Overall Progress: %p%')
        self.overall_progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.overall_progress_bar.setTextVisible(True)
        progress_bars_layout.addWidget(self.overall_progress_bar)

        # Current File Progress Bar
        self.current_file_progress_bar = QProgressBar()
        self.current_file_progress_bar.setMaximum(100)
        self.current_file_progress_bar.setValue(0)
        self.current_file_progress_bar.setFormat('Current File Progress: %p%')
        self.current_file_progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.current_file_progress_bar.setTextVisible(True)
        progress_bars_layout.addWidget(self.current_file_progress_bar)

        progress_info_layout.addLayout(progress_bars_layout)

        # Add the progress_info_layout to the output_section
        output_section.addLayout(progress_info_layout)

        # Wrap sections into QWidgets
        media_widget = QWidget()
        media_widget.setLayout(media_section)

        progress_widget = QWidget()
        progress_widget.setLayout(progress_section)

        output_widget = QWidget()
        output_widget.setLayout(output_section)

        # Create a QSplitter
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.addWidget(media_widget)
        self.splitter.addWidget(progress_widget)
        self.splitter.addWidget(output_widget)

        # Optionally set initial sizes
        self.splitter.setSizes([MEDIA_LIST_HEIGHT, PROGRESS_AREA_HEIGHT, OUTPUT_AREA_HEIGHT])

        # Add the splitter to the main_layout
        main_layout.addWidget(self.splitter)

        self.setLayout(main_layout)

        ##### 7. Connect Signals #####
        self.check_media_btn.clicked.connect(self.check_media)
        self.start_encoding_btn.clicked.connect(self.start_encoding)
        self.clear_media_btn.clicked.connect(self.clear_media_list)
        self.target_size_input.textChanged.connect(self.on_settings_changed)
        self.audio_bitrate_input.textChanged.connect(self.on_settings_changed)
        self.preset_combo.currentIndexChanged.connect(self.on_preset_changed)
        self.media_list.itemSelectionChanged.connect(self.on_settings_changed)
        self.dest_input.textChanged.connect(self.on_destination_changed)
        self.dest_browse_btn.clicked.connect(self.browse_destination_folder)
        self.media_list.deletePressed.connect(self.delete_selected_media)
        self.media_list.audioSelectionRequested.connect(self.open_audio_selection_dialog)  # Connect new signal

        # Connect header resize signal to save column widths
        header = self.media_list.header()
        header.sectionResized.connect(self.on_section_resized)

        # Connect the delete source combo box signal
        self.delete_source_combo.currentIndexChanged.connect(self.on_delete_source_changed)

        # Connect the encoder combo box signal
        self.encoder_combo.currentIndexChanged.connect(self.on_encoder_changed)

        # Connect the priority combo box signal
        self.priority_combo.currentIndexChanged.connect(self.on_priority_changed)

        # **Connect the audio encoder combo box signal**
        self.audio_encoder_combo.currentIndexChanged.connect(self.on_audio_encoder_changed)

        # Connect signals for variable bitrate and multi-pass checkboxes
        self.variable_bitrate_checkbox.stateChanged.connect(self.on_variable_bitrate_changed)
        self.multi_pass_checkbox.stateChanged.connect(self.on_multi_pass_changed)

    def update_multi_pass_state(self):
        # Check if the selected encoder is a hardware encoder
        hardware_encoders = ['nvenc_h264', 'nvenc_h265', 'nvenc_h265_10bit']
        is_hardware_encoder = self.encoder_combo.currentText() in hardware_encoders

        if self.variable_bitrate_checkbox.isChecked() or is_hardware_encoder:
            # Disable and grey out the Multi-Pass checkbox
            self.multi_pass_checkbox.setChecked(False)
            self.multi_pass_checkbox.setEnabled(False)
            self.multi_pass_checkbox.setStyleSheet("color: grey;")
        else:
            # Enable the Multi-Pass checkbox
            self.multi_pass_checkbox.setEnabled(True)
            self.multi_pass_checkbox.setStyleSheet("")  # Reset to default style
            # Default to checked when enabled
            self.multi_pass_checkbox.setChecked(True)

    def on_preset_changed(self):
        self.selected_preset = self.preset_combo.currentText()
        if self.selected_preset != 'None':
            # Ensure 'None' is in the encoder combos
            if 'None' not in [self.encoder_combo.itemText(i) for i in range(self.encoder_combo.count())]:
                self.encoder_combo.insertItem(0, 'None')
            if 'None' not in [self.audio_encoder_combo.itemText(i) for i in range(self.audio_encoder_combo.count())]:
                self.audio_encoder_combo.insertItem(0, 'None')
            # Set current selection to 'None'
            self.encoder_combo.setCurrentText('None')
            self.audio_encoder_combo.setCurrentText('None')
        else:
            # Remove 'None' from encoder combos if present
            index = self.encoder_combo.findText('None')
            if index != -1:
                self.encoder_combo.removeItem(index)
            index = self.audio_encoder_combo.findText('None')
            if index != -1:
                self.audio_encoder_combo.removeItem(index)
            # Set encoder selections to default values if necessary
            if self.encoder_combo.currentIndex() == -1:
                self.encoder_combo.setCurrentIndex(0)
            if self.audio_encoder_combo.currentIndex() == -1:
                self.audio_encoder_combo.setCurrentIndex(0)
        # Save selected preset
        self.save_setting('selected_preset', self.selected_preset)
        # Call settings changed handler
        self.on_settings_changed()

    def on_variable_bitrate_changed(self):
        self.update_multi_pass_state()
        self.on_settings_changed()
        
    def on_multi_pass_changed(self):
        self.on_settings_changed()

    def on_encoder_changed(self):
        self.selected_encoder = self.encoder_combo.currentText()
        self.save_setting('selected_encoder', self.selected_encoder)
        self.update_multi_pass_state()
        self.on_settings_changed()

    def on_audio_encoder_changed(self):
        self.selected_audio_encoder = self.audio_encoder_combo.currentText()
        self.save_setting('selected_audio_encoder', self.selected_audio_encoder)
        # Disable the audio bitrate input if 'copy' or 'None' is selected
        if self.selected_audio_encoder in ('copy', 'None'):
            self.audio_bitrate_input.setEnabled(False)
            self.audio_bitrate_input.clear()  # Clear the input field
        else:
            self.audio_bitrate_input.setEnabled(True)
        self.on_settings_changed()

    def on_priority_changed(self):
        self.selected_priority = self.priority_combo.currentText()
        self.save_setting('selected_priority', self.selected_priority)
        self.on_settings_changed()

    def on_section_resized(self, logicalIndex, oldSize, newSize):
        # Save the new width to the database
        self.save_column_width(logicalIndex, newSize)

    def browse_destination_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder:
            self.dest_input.setText(folder)

    def on_destination_changed(self):
        self.destination_folder = self.dest_input.text()
        self.save_setting('destination_folder', self.destination_folder)
        self.on_settings_changed()

    def load_settings(self):
        # Load destination folder from the database
        self.destination_folder = self.load_setting('destination_folder', '')
        self.dest_input.setText(self.destination_folder)

        # Load column widths
        self.load_column_widths()

        # Load window size
        window_width = self.load_setting('window_width')
        window_height = self.load_setting('window_height')
        self.window_size_loaded = False  # Initialize flag
        if window_width and window_height:
            try:
                window_width = int(window_width)
                window_height = int(window_height)
                self.resize(window_width, window_height)
                self.window_size_loaded = True
            except ValueError:
                pass  # Use default size if values are invalid

        # Load window position
        window_x = self.load_setting('window_x')
        window_y = self.load_setting('window_y')
        if window_x and window_y:
            try:
                window_x = int(window_x)
                window_y = int(window_y)
                self.move(window_x, window_y)
            except ValueError:
                pass  # Use default position if values are invalid

        # Load delete source files setting
        delete_source_files = self.load_setting('delete_source_files', 'no')  # Default to 'no'
        delete_source_files_capitalized = delete_source_files.capitalize()  # Capitalize the first letter
        index = self.delete_source_combo.findText(delete_source_files_capitalized)
        if index != -1:
            self.delete_source_combo.setCurrentIndex(index)
        else:
            self.delete_source_combo.setCurrentIndex(2)  # Default to 'No' if not found

        # Load selected encoder
        self.selected_encoder = self.load_setting('selected_encoder', 'x265')
        index = self.encoder_combo.findText(self.selected_encoder)
        if index != -1:
            self.encoder_combo.setCurrentIndex(index)
        else:
            self.encoder_combo.setCurrentIndex(0)  # Default to first encoder if not found

        # Load selected audio encoder
        self.selected_audio_encoder = self.load_setting('selected_audio_encoder', 'av_aac')
        index = self.audio_encoder_combo.findText(self.selected_audio_encoder)
        if index != -1:
            self.audio_encoder_combo.setCurrentIndex(index)
        else:
            self.audio_encoder_combo.setCurrentIndex(0)  # Default to first audio encoder if not found

        # Disable audio bitrate input if 'copy' or 'None' is selected
        if self.selected_audio_encoder in ('copy', 'None'):
            self.audio_bitrate_input.setEnabled(False)
        else:
            self.audio_bitrate_input.setEnabled(True)

        # Load selected preset
        self.selected_preset = self.load_setting('selected_preset', 'None')
        index = self.preset_combo.findText(self.selected_preset)
        if index != -1:
            self.preset_combo.setCurrentIndex(index)
        else:
            self.preset_combo.setCurrentIndex(0)  # Default to 'None' if not found

        # Load selected process priority
        self.selected_priority = self.load_setting('selected_priority', 'Normal')
        index = self.priority_combo.findText(self.selected_priority)
        if index != -1:
            self.priority_combo.setCurrentIndex(index)
        else:
            self.priority_combo.setCurrentIndex(0)  # Default to 'Normal' if not found

        # Disable or enable audio bitrate input based on selected audio encoder
        if self.selected_audio_encoder in ('copy', 'None'):
            self.audio_bitrate_input.setEnabled(False)
        else:
            self.audio_bitrate_input.setEnabled(True)
            
        # Set Multi-Pass checkbox to unchecked by default
        self.multi_pass_checkbox.setChecked(False)
        # Update Multi-Pass state based on current settings
        self.update_multi_pass_state()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        file_paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    for file in files:
                        file_paths.append(os.path.join(root, file))
            else:
                file_paths.append(path)
        self.add_media_worker = AddMediaWorker(file_paths, self.mediainfo_exe)
        self.add_media_worker.progress.connect(self.add_media_files_incrementally)  # Use incremental update
        self.add_media_worker.finished.connect(self.on_add_media_finished)
        self.add_media_worker.start()
        self.on_settings_changed()

    def add_media_files_incrementally(self, media_files):
        for media_info in media_files:
            display_info = [
                media_info['filename'],
                media_info['duration'],
                media_info['video'],
                media_info['audio'],
                media_info['size']
            ]
            item = QTreeWidgetItem(display_info)
            media = {'path': media_info['path'], 'info': media_info, 'item': item}
            
            # Select all audio tracks by default
            media['selected_audio_tracks'] = list(range(len(media_info['audio_tracks'])))  # All tracks selected by default
            item.media_dict = media  # Attach media dict to the item
            
            self.media_files.append(media)
            self.media_list.addTopLevelItem(item)

        # Automatically select the topmost item in the media list
        if self.media_list.topLevelItemCount() > 0:
            self.media_list.clearSelection()  # Clear any existing selection
            top_item = self.media_list.topLevelItem(0)  # Get the first (topmost) item
            self.media_list.setCurrentItem(top_item)  # Set it as the currently selected item

        self.update_info_panel()  # Update info panel after adding media files

    def on_add_media_finished(self):
        self.on_settings_changed()

    def check_media(self):
        # Clear progress area
        self.progress_area.clear()

        # Disable buttons during processing
        self.check_media_btn.setEnabled(False)
        self.start_encoding_btn.setEnabled(False)
        self.clear_media_btn.setEnabled(False)

        # Initialize and start the check media worker
        self.check_media_worker = CheckMediaWorker(
            self.media_files,
            self.mediainfo_exe,
            self.mkvpropedit_exe,
            per_file_output_only=PER_FILE_OUTPUT_ONLY  # Add this line
        )
        self.check_media_worker.progress.connect(self.update_progress)
        self.check_media_worker.clear_progress.connect(self.clear_progress_areas)
        self.check_media_worker.finished.connect(self.check_media_finished)
        self.check_media_worker.start()

    def check_media_finished(self):
        # Refresh media info to reflect updates
        self.refresh_media_info()

        # Re-enable buttons based on settings
        self.on_settings_changed()

    def refresh_media_info(self):
        """
        Refresh the media information displayed in the GUI.
        """
        self.media_list.clear()
        updated_media_files = []
        for media in self.media_files:
            file_path = media['path']
            media_info = self.get_media_info(file_path)
            if media_info:
                display_info = [
                    media_info['filename'],
                    media_info['duration'],
                    media_info['video'],
                    media_info['audio'],
                    media_info['size']
                ]
            else:
                display_info = [os.path.basename(file_path), "Error getting info", "", "", ""]
            item = QTreeWidgetItem(display_info)
            media = {'path': file_path, 'info': media_info, 'item': item}
            media['selected_audio_tracks'] = list(range(len(media_info['audio_tracks']))) if media_info and 'audio_tracks' in media_info else []
            item.media_dict = media
            updated_media_files.append(media)
            self.media_list.addTopLevelItem(item)
        self.media_files = updated_media_files

    def get_media_info(self, file_path):
        try:
            output = subprocess.check_output(
                [self.mediainfo_exe, '--Output=JSON', file_path],
                encoding='utf-8',
                errors='replace',
                text=True
            )
            data = json.loads(output)
            tracks = data.get('media', {}).get('track', [])

            # Initialize variables
            general_track = None
            video_track = None
            audio_tracks = []
            total_audio_bitrate_kbps = 0  # Initialize total audio bitrate

            for track in tracks:
                if track.get('@type') == 'General':
                    general_track = track
                elif track.get('@type') == 'Video' and not video_track:
                    video_track = track
                elif track.get('@type') == 'Audio':
                    audio_tracks.append(track)
                    # Accumulate audio bitrate
                    bitrate_str = track.get('BitRate')
                    if bitrate_str and str(bitrate_str).lower() != "n/a":
                        try:
                            total_audio_bitrate_kbps += float(bitrate_str) / 1000  # Convert bps to kbps
                        except ValueError:
                            pass  # Ignore invalid bitrate values

            if not general_track or not video_track or not audio_tracks:
                raise ValueError("Missing required track information.")

            file_size = os.path.getsize(file_path)

            # Define a function to format bitrate with '.' as thousands separator
            def format_bitrate_kbps(value):
                s = f"{value:,.0f}"  # Format with ',' as thousands separator
                return s.replace(',', '.')

            # Video bitrate formatting with enhanced handling
            video_info_list = []
            if video_track:
                # Collect video details
                video_codec = video_track.get('Format', 'Unknown')
                video_bitrate = video_track.get('BitRate')
                video_bitrate_formatted = "Unknown"
                if video_bitrate and str(video_bitrate).lower() != "n/a":
                    try:
                        video_bitrate_float = float(video_bitrate) / 1000  # Convert to kbps
                        video_bitrate_formatted = format_bitrate_kbps(video_bitrate_float)
                    except ValueError:
                        pass

                # Resolution
                width = video_track.get('Width', 'Unknown')
                height = video_track.get('Height', 'Unknown')
                resolution = f"{width}x{height}"

                # Frame rate
                frame_rate = video_track.get('FrameRate', 'Unknown')

                # Build video info list
                video_info_list.append(f"Codec: {video_codec}")
                video_info_list.append(f"Bitrate: {video_bitrate_formatted} kbps")
                video_info_list.append(f"Resolution: {resolution}")
                video_info_list.append(f"Frame Rate: {frame_rate} fps")

                # Combine into multi-line string
                video_info = "\n".join(video_info_list)
                # For display in the column, use a summary
                video_summary = f"{video_codec} {video_bitrate_formatted} kbps"
            else:
                video_info = "Unknown"
                video_summary = "Unknown"

            # Audio bitrate and language formatting
            audio_info_list = []
            for idx, audio_track in enumerate(audio_tracks, start=1):
                bitrate_str = audio_track.get('BitRate')
                language_str = audio_track.get('Language/String') or audio_track.get('Language') or "Unknown"
                # Convert language codes to full names using the shared function
                full_language = get_full_language_name(language_str)
                if isinstance(full_language, list):
                    full_language = ', '.join(full_language)
                if bitrate_str and isinstance(bitrate_str, (int, float, str)) and str(bitrate_str).lower() != "n/a":
                    try:
                        bitrate_float = float(bitrate_str) / 1000  # Convert to kbps
                        audio_codec = audio_track.get('Format', 'Unknown')
                        bitrate_display = f"{int(bitrate_float)} kbps" if bitrate_float else "Unknown Bitrate"
                    except ValueError:
                        bitrate_display = "Unknown Bitrate"
                else:
                    bitrate_display = "Unknown Bitrate"

                # Retrieve the Title if available
                title = audio_track.get('Title', '').strip()

                if title:
                    # Include the Title in the display if it exists
                    audio_info = f"{idx}: {title} - {audio_track.get('Format', 'Unknown')} {bitrate_display} [{full_language}]"
                else:
                    # Fallback to original format if Title is not available
                    audio_info = f"{idx}: {audio_track.get('Format', 'Unknown')} {bitrate_display} [{full_language}]"

                audio_info_list.append(audio_info)

            audio_info = "\n".join(audio_info_list)

            # Get duration and format it
            duration_str = general_track.get('Duration')
            if duration_str is None or str(duration_str).lower() == "n/a":
                duration_formatted = "Unknown"
                duration_seconds = None
            else:
                try:
                    duration_seconds = float(duration_str)
                    duration_formatted = self.format_duration(duration_seconds)
                except ValueError:
                    duration_formatted = "Unknown"
                    duration_seconds = None

            # Return info as a dict
            info = {
                'filename': os.path.basename(file_path),
                'duration': duration_formatted,
                'duration_seconds': duration_seconds,
                'video': video_summary,      # Display summary in the column
                'video_info': video_info,    # Store detailed info for tooltip
                'audio': audio_info,
                'size': f"{int(file_size / (1024 * 1024))} MB",
                'size_bytes': file_size,
                'total_audio_bitrate_kbps': total_audio_bitrate_kbps,  # Store total audio bitrate
                'path': file_path,
                'audio_tracks': audio_tracks  # Store all audio tracks for selection
            }
            return info
        except Exception as e:
            self.update_progress(f"Error getting media info for {file_path}: {e}")
            return None

    def format_duration(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h:{minutes}min"

    def start_encoding(self):
        # Clear output area
        self.output_area.clear()
        self.progress_area.clear()

        # Reset progress indicators
        self.overall_progress_bar.setValue(0)
        self.current_file_progress_bar.setValue(0)
        self.current_file_label.setText("Current File: None")
        self.current_file_label.setVisible(True)  # Show the label

        # Disable buttons during encoding
        self.check_media_btn.setEnabled(False)
        self.start_encoding_btn.setEnabled(False)
        self.clear_media_btn.setEnabled(False)

        # Set tooltip to explain why the button is disabled
        self.start_encoding_btn.setToolTip("Encoding is in progress.")

        self.encoding_in_progress = True  # Add this line

        # Get selected preset and preset file
        if self.selected_preset == 'None':
            preset_file = None
            preset_name = None
        else:
            preset_file = self.preset_files[self.selected_preset]
            preset_name = self.selected_preset

        # Get selected encoder and process priority
        self.selected_encoder = self.encoder_combo.currentText()
        self.selected_priority = self.priority_combo.currentText()

        # Get delete source files option
        delete_source_files = self.delete_source_combo.currentText()

        # Get selected audio encoder
        self.selected_audio_encoder = self.audio_encoder_combo.currentText()

        # Create a list of selected audio tracks for each media file
        selected_audio_tracks = []
        for media in self.media_files:
            selected_audio_tracks.append(media['selected_audio_tracks'])  # Add the selected audio tracks

        # Get variable bitrate checkbox value
        variable_bitrate = self.variable_bitrate_checkbox.isChecked()

        # Initialize and start the encoding worker
        self.encoding_worker = EncodingWorker(
            self.media_files,
            self.handbrake_cli,
            self.mediainfo_exe,
            self.target_size_mb,
            self.audio_bitrate,
            preset_file,
            preset_name,
            self.destination_folder,
            per_file_output_only=PER_FILE_OUTPUT_ONLY,
            delete_source_files=delete_source_files,
            selected_encoder=self.selected_encoder,
            selected_audio_encoder=self.selected_audio_encoder,
            process_priority=self.selected_priority,
            selected_audio_tracks=selected_audio_tracks,
            variable_bitrate=variable_bitrate,
            ffmpeg_exe=self.ffmpeg_exe,
            multi_pass=self.multi_pass_checkbox.isChecked()  # Add this line
        )
        self.encoding_worker.progress.connect(self.update_progress)  # Send progress to PROGRESS_AREA
        self.encoding_worker.handbrake_output.connect(self.update_output)
        self.encoding_worker.overall_progress.connect(self.overall_progress_bar.setValue)  # Direct connection
        self.encoding_worker.current_file.connect(self.update_current_file_label)  # Update current file label
        self.encoding_worker.current_file_progress.connect(self.current_file_progress_bar.setValue)  # Update current file progress bar
        self.encoding_worker.finished.connect(self.encoding_finished)
        self.encoding_worker.clear_progress.connect(self.clear_progress_areas)  # Connect the new signal
        self.encoding_worker.delete_file_signal.connect(self.handle_delete_source_file)  # Connect the new signal
        self.encoding_worker.start()

    def clear_progress_areas(self):
        self.progress_area.clear()
        self.output_area.clear()

    def encoding_finished(self):
        self.current_file_label.setText("Current File: None")
        self.current_file_label.setVisible(False)  # Hide the label
        self.encoding_in_progress = False  # Add this line
        # Re-enable buttons based on settings
        self.on_settings_changed()

        # Reset the tooltip
        self.start_encoding_btn.setToolTip("")

    def handle_delete_source_file(self, file_path, delete_source_files_option):
        file_name = os.path.basename(file_path)
        option = delete_source_files_option.lower()  # Convert to lowercase
        if option == 'auto':
            # Automatically delete the source file
            try:
                os.remove(file_path)
                self.update_progress(f"🗑️ Deleted source file: {file_name}")
            except Exception as e:
                self.update_progress(f"❌ Error deleting source file {file_name}: {e}")
        elif option == 'ask':
            # Prompt the user
            reply = QMessageBox.question(self, 'Delete Source File',
                                         f"Do you want to delete the source file '{file_name}'?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                try:
                    os.remove(file_path)
                    self.update_progress(f"🗑️ Deleted source file: {file_name}")
                except Exception as e:
                    self.update_progress(f"❌ Error deleting source file {file_name}: {e}")
            else:
                self.update_progress(f"ℹ️ Source file kept: {file_name}")
        elif option == 'no':
            # Do not delete
            self.update_progress(f"ℹ️ Source file kept: {file_name}")
        else:
            # Unrecognized option
            self.update_progress(f"⚠️ Unrecognized delete source option '{delete_source_files_option}' for file: {file_name}")

    def update_progress(self, text):
        # Append text to the progress area with proper formatting
        self.progress_area.append(text)
        # Scroll to the bottom to ensure the latest message is visible
        self.progress_area.verticalScrollBar().setValue(self.progress_area.verticalScrollBar().maximum())

    def update_output(self, text):
        self.output_area.append(text)

    def update_current_file_label(self, text):
        # Update the current file label
        self.current_file_label.setText(f"Current File: {text}")

    def on_settings_changed(self):
        self.target_size_mb = self.target_size_input.text()
        self.audio_bitrate = self.audio_bitrate_input.text().strip() if self.audio_bitrate_input.text().strip() else None
        self.selected_preset = self.preset_combo.currentText()
        self.destination_folder = self.dest_input.text()
        self.selected_encoder = self.encoder_combo.currentText()
        self.selected_audio_encoder = self.audio_encoder_combo.currentText()
        self.selected_priority = self.priority_combo.currentText()
        self.update_info_panel()

        # Validate inputs for Start Encoding button
        inputs_valid = True
        validation_errors = []  # New list to collect validation errors

        # Check if media files are present
        if not self.media_files:
            inputs_valid = False
            validation_errors.append("No media files added.")

        # Validate target size
        try:
            float(self.target_size_mb)
        except ValueError:
            inputs_valid = False
            validation_errors.append("Invalid target size.")

        # Validate destination folder
        if not self.destination_folder or not os.path.isdir(self.destination_folder):
            inputs_valid = False
            validation_errors.append("Invalid destination folder.")

        # If audio encoder is not 'copy' or 'None', require audio bitrate
        if self.selected_audio_encoder not in ('copy', 'None'):
            max_selected_audio_tracks = 0
            for media in self.media_files:
                num_selected_tracks = len(media.get('selected_audio_tracks', []))
                max_selected_audio_tracks = max(max_selected_audio_tracks, num_selected_tracks)

            if max_selected_audio_tracks > 0:
                # Audio bitrate is required
                if not self.audio_bitrate:
                    inputs_valid = False
                    validation_errors.append("Audio bitrate is required.")
                else:
                    bitrate_values = [bitrate.strip() for bitrate in self.audio_bitrate.split(',')]
                    if len(bitrate_values) != max_selected_audio_tracks:
                        inputs_valid = False
                        validation_errors.append(
                            f"Number of audio bitrate values ({len(bitrate_values)}) does not match number of selected audio tracks ({max_selected_audio_tracks})."
                        )
                    else:
                        for bitrate in bitrate_values:
                            if not bitrate.isdigit() or int(bitrate) <= 0:
                                inputs_valid = False
                                validation_errors.append(f"Invalid audio bitrate value: {bitrate}")
                                break
            else:
                # No audio tracks selected, bitrate is not required
                pass
        else:
            # Audio encoder is 'copy' or 'None', bitrate input is ignored
            pass

        # Validate preset selection
        if self.selected_preset != 'None' and self.selected_preset not in self.preset_files:
            inputs_valid = False
            validation_errors.append("Invalid preset selected.")

        if self.encoding_in_progress:
            # Disable the Start Encoding button and set tooltip
            self.start_encoding_btn.setEnabled(False)
            self.start_encoding_btn.setToolTip("Encoding is in progress.")
            # Also, disable other buttons if necessary
            self.check_media_btn.setEnabled(False)
            self.clear_media_btn.setEnabled(False)
        else:
            # Enable or disable the Start Encoding button based on validation
            self.start_encoding_btn.setEnabled(inputs_valid)
            self.check_media_btn.setEnabled(bool(self.media_files))  # Enabled if any media files are present
            self.clear_media_btn.setEnabled(bool(self.media_files))

            # Set tooltip on Start Encoding button
            if inputs_valid:
                self.start_encoding_btn.setToolTip("")
            else:
                # Set tooltip with validation errors
                tooltip_text = "Cannot start encoding due to the following reasons:\n"
                tooltip_text += "\n".join(validation_errors)
                self.start_encoding_btn.setToolTip(tooltip_text)

    def delete_selected_media(self):
        selected_items = self.media_list.selectedItems()
        for item in selected_items:
            media_dict = item.media_dict
            if media_dict in self.media_files:
                self.media_files.remove(media_dict)
            index = self.media_list.indexOfTopLevelItem(item)
            self.media_list.takeTopLevelItem(index)
        self.on_settings_changed()  # Update button states if necessary

    def clear_media_list(self):
        # Clear media list and media_files
        self.media_list.clear()
        self.media_files = []

        # Clear progress area and output area
        self.progress_area.clear()
        self.output_area.clear()

        # Reset progress bars
        self.overall_progress_bar.setValue(0)
        self.current_file_progress_bar.setValue(0)

        # Reset current file label
        self.current_file_label.setText("Current File: None")
        self.current_file_label.setVisible(False)  # Hide the label

        # Update button states
        self.on_settings_changed()  # Update button states if necessary

    def closeEvent(self, event):
        # Save window size
        window_size = self.size()
        self.save_setting('window_width', str(window_size.width()))
        self.save_setting('window_height', str(window_size.height()))

        # Save window position
        window_pos = self.pos()
        self.save_setting('window_x', str(window_pos.x()))
        self.save_setting('window_y', str(window_pos.y()))

        # Save splitter sizes
        splitter_sizes = self.splitter.sizes()
        self.save_setting('splitter_sizes', json.dumps(splitter_sizes))

        # Save delete source files setting
        delete_source_value = self.delete_source_combo.currentText()
        self.save_setting('delete_source_files', delete_source_value)

        # Save selected process priority
        self.save_setting('selected_priority', self.priority_combo.currentText())

        # Save selected encoder
        self.save_setting('selected_encoder', self.selected_encoder)

        # Save selected audio encoder
        self.save_setting('selected_audio_encoder', self.selected_audio_encoder)

        # Save selected preset
        self.save_setting('selected_preset', self.preset_combo.currentText())

        # Close the database connection when the application is closed
        if hasattr(self, 'conn'):
            self.conn.close()
        event.accept()

    def on_delete_source_changed(self):
        delete_source_value = self.delete_source_combo.currentText().lower()  # Convert to lowercase
        self.save_setting('delete_source_files', delete_source_value)
        self.on_settings_changed()

    def open_audio_selection_dialog(self, items):
        # items is a list of QTreeWidgetItem
        if not items:
            return

        # Collect the maximum number of audio tracks among selected items
        max_audio_tracks = 0
        for item in items:
            media_dict = item.media_dict
            audio_tracks = media_dict['info'].get('audio_tracks', [])
            if len(audio_tracks) > max_audio_tracks:
                max_audio_tracks = len(audio_tracks)

        if max_audio_tracks == 0:
            QMessageBox.information(self, "No Audio Tracks", "No audio tracks found in the selected media files.")
            return

        # Create track labels
        track_labels = [f"Track {i+1}" for i in range(max_audio_tracks)]

        dialog = AudioSelectionDialog(track_labels, parent=self)

        # Show the dialog
        if dialog.exec_() == QDialog.Accepted:
            selected_tracks = dialog.get_selected_tracks()
            # Apply selected tracks to all selected items
            for item in items:
                media_dict = item.media_dict
                audio_tracks = media_dict['info'].get('audio_tracks', [])
                # Adjust selected tracks to available tracks in this media
                available_tracks = len(audio_tracks)
                adjusted_selected_tracks = [idx for idx in selected_tracks if idx < available_tracks]
                media_dict['selected_audio_tracks'] = adjusted_selected_tracks

                # Update the display
                # Build audio info based on selected tracks
                selected_audio_info = []
                for idx in adjusted_selected_tracks:
                    track = audio_tracks[idx]
                    bitrate = track.get('BitRate')
                    bitrate_display = "Unknown Bitrate"
                    if bitrate and isinstance(bitrate, (int, float, str)) and str(bitrate).lower() != "n/a":
                        try:
                            bitrate_float = float(bitrate)
                            bitrate_kbps = int(bitrate_float / 1000) if bitrate_float else 0
                            bitrate_display = f"{bitrate_kbps} kbps" if bitrate_kbps > 0 else "Unknown Bitrate"
                        except ValueError:
                            pass  # Keep as "Unknown Bitrate" if conversion fails
                    format_str = track.get('Format', 'Unknown')
                    audio_info = f"{idx+1}: {format_str} {bitrate_display}"
                    selected_audio_info.append(audio_info)
                media_dict['info']['audio'] = "\n".join(selected_audio_info) if selected_audio_info else "No Audio Tracks Selected"
                item.setText(COL_AUDIO, media_dict['info']['audio'])

            # Update the info panel
            self.update_info_panel()

            # **Trigger settings change to update the "Start Encoding" button immediately**
            self.on_settings_changed()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = MediaEncoderGUI()
    gui.show()
    sys.exit(app.exec_())
