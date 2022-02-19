# plex-required-bitrate.py

plex-required-bitrate.py is a Python3 script which calculates the upload bitrate required to stream the video track from a video file for different client buffer sizes.

This script is designed to produce results as close to those produced by Plex itself and does so with the same buffer sizes that Plex uses.

Note this code is also available as a Gist [here](https://gist.github.com/martinpickett/156e2830541bfdba513aff1c25c24b4e) if you find it more convenient.

### Usage

`plex-required-bitrate.py FILE`

A list of additional options can be found in the help message accessed by running `plex-required-bitrate.py --help`.

### Requirements

- Python 3.2
- FFprobe

### Expectations

This script dos not complete immediately. On my computer (Intel Core i5 7360U) it takes  15-20 seconds depending on the length of the input file.

### Caveats

This script does not always produce the correct bitrate! For the vast majority of my test videos, it does produce the same bitrate as Plex to within 2 kb/s (plus or minus 1 kb/s), however for certain videos, especially at small buffer sizes, the inaccuracy increases. The biggest error I have seen is 41 kb/s. If anyone can find the bug, please open an issue and let me know.

### Alternatives

Sam Hutchins wrote his own Python script to solve the same problem which you can find [here](https://gist.github.com/samhutchins/1f7877120ad84d0c522bd9619dcde8b5).
