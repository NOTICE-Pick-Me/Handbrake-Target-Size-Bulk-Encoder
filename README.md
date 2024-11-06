
# HandBrake: Target Size Bulk Encoder
<img src="https://i.imgur.com/lpTTsE9.png" width=75% height=75%>

A user-friendly GUI application for batch encoding media files using HandBrakeCLI, allowing you to set a target file size for your videos. Supports both average bitrate (`-b`) and constant quality (`-q`) encoding modes, with options to use HandBrake JSON presets and overwrite settings via the GUI.

## Features

-   **Target Size Encoding**: Encode videos to a specific file size using either average bitrate (`-b`) or constant quality (`-q`) modes.
-   **HandBrake Preset Integration**: Import and use HandBrake JSON presets for encoding settings.
-   **Preset Overwrite**: Overwrite specific preset settings directly from the GUI or opt not to use presets at all.
-   **Batch Processing**: Add multiple media files or entire folders for batch encoding.
-   **Process Priority Control**: Adjust the encoding process priority to manage system resources.
-   **Delete Source Files**: Option to automatically delete source files after successful encoding.

## Prerequisites
-   **Python 3.x**: Ensure you have Python 3 installed on your system.
-   **PyQt5**: GUI elements
-   **pycountry**: ISO 639 language codes

**Install Required Python Packages**

Install the required packages using `pip`:

    pip install PyQt5
    pip install pycountry


## Instructions
**Place Preset Files (Optional)**

If you plan to use exported HandBrake presets, create a `__presets__` directory inside `__dependencies__` and place your JSON preset files there.

**Note**:
-   Ensure that the JSON file name matches the preset name inside the file.


**Selecting Audio Tracks (Optional)**

By default, all audio tracks in your media files are selected for encoding. If you wish to customize which audio tracks are included in the encoded output, you can easily select specific audio tracks by right-clicking on selected media.

**Note**:
-   When specifying the audio bitrate in the **"Audio Bitrate (kbps)"** field, if you have selected multiple audio tracks, separate the bitrate values with commas (e.g., `"128,256"`). This ensures that each selected audio track is assigned the correct bitrate.

## Acknowledgements
This application utilizes the following third-party software:
-   [HandBrake](https://handbrake.fr/) is an open-source video transcoder.
-   [MediaInfo](https://mediaarea.net/en/MediaInfo) provides technical and tag information about video and audio files.
-   [MKVToolNix](https://mkvtoolnix.download/) is a set of tools to create, alter, and inspect Matroska files.
-   [FFmpeg](https://ffmpeg.org/) is a complete, cross-platform solution to record, convert, and stream audio and video.
