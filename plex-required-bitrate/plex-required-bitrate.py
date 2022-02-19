#!/usr/bin/env python3

from argparse import ArgumentParser
import os
import json
import math
from subprocess import run, DEVNULL, PIPE
from fractions import Fraction
from multiprocessing import Pool
from itertools import accumulate

version = f"""\
{os.path.basename(__file__)} 2022.02.19
Martin Pickett
"""

help_string = f"""\
Calculate the Plex Required Bitrates for the video stream in a video file.

Usage: {os.path.basename(__file__)} [OPTIONS] FILE

Options:
-h,   --help                print help message and exit
-v,   --version             print version information and exit

Requires FFprobe.
"""

def main():
	parser = ArgumentParser(add_help=False)
	parser.add_argument("file", nargs="?")
	parser.add_argument("-h", "--help", action="store_true", default=False)
	parser.add_argument("-v", "--version", action="store_true", default=False)
	args = parser.parse_args()	
	
	# Print version and exit
	if args.version:
		print(version)
		exit()

	# Print help and exit
	if args.help:
		print(help_string)
		exit()

	# Checks existence of file
	if not os.path.isfile(args.file):
		exit(f"Error: File {args.file} does not exist")
	
	# Information for user
	print("Information: Reading file...")
	
	# Get list of frame sizes and fps from input file
	frames, fps = get_frames(args.file)
		
	# Coarse check for valid input file
	if not len(frames) > 0:
		exit(f"Error: Input file {args.file} invalid")
	
	# Information for user
	print("Information: Starting rate value calculations for Plex buffer sizes...")
	
	# Standard Plex buffer sizes
	plex_buffers_nominal = [5, 10, 25, 50, 75, 100, 250, 500] # in megabytes
	plex_buffers_actual = [x*7200000 for x in plex_buffers_nominal] # in bits
	
	# Create removal_time list
	t_remove = [5 + n/fps for n in range(len(frames))]
	
	#Calculate rates in parallel and convert to kb/s
	args = [ (frames, fps, x, t_remove) for x in plex_buffers_actual ]
	with Pool(maxtasksperchild=1) as p:
		rates = p.starmap(bisection_method, args)
	rates = [math.ceil(rate/1000) for rate in rates]
	
	print("       Plex Buffer (MB):      5      10      25      50      75     100     250     500     ")
	print(f"Required Bitrate (kb/s): {rates[0]:6.0f}  {rates[1]:6.0f}  {rates[2]:6.0f}  {rates[3]:6.0f}  {rates[4]:6.0f}  {rates[5]:6.0f}  {rates[6]:6.0f}  {rates[7]:6.0f}")
	exit()
	

# Bisection Method - Returns minimum rate (float) in bits per second
def bisection_method(frames, fps, buffer, t_remove):
	accuracy = 1
	
	# Initial guesses for rate. a = lower limit, b = upper limit
	a = (sum(frames) / len(frames)) * fps
	b = max(frames) * fps
	
	# Loop and minimise f_c (make f_c as close to zero as possible)
	while (b - a) > accuracy:
		c = (a + b) * 0.5
		f_c = calculate_buffer_size(frames, c, fps, t_remove)
		if f_c is None:
			a = c
		else:
			if f_c - buffer > 0:
				a = c
			else:
				b = c

	# return the higher of the two bracketing values
	return b


# Returns max buffer size in bits (this will always be an integer value)
def calculate_buffer_size(frames, rate, fps, t_remove):
	# maximum download rate (maxrate) in bits per second
	
	# Two lists, initial arrival times and final arrival times
	t_arrive_i = [t - s/rate for t, s in zip(t_remove, frames)]
	t_arrive_f = t_remove.copy()
	
	# Adjust arrival time lists to eliminate any overlapping between frames
	for i in range(len(t_arrive_i)-1, 0, -1):
		if t_arrive_i[i] < t_arrive_f[i-1]:
			t_arrive_i[i-1] = t_arrive_i[i] - frames[i-1]/rate
			t_arrive_f[i-1] = t_arrive_i[i]
	
	# If we have moved first initial arrival time -'ve then stream invalid
	if t_arrive_i[0] < 0:
		return None
	
	# Create empty timeline and frame to remove counter
	timeline = []
	f_remove = 0
	
	# This speeds up the next loop, which is good
	timeline_append = timeline.append
	
	# Create timeline of +size and -size values
	for t_ai, t_af, size in zip(t_arrive_i, t_arrive_f, frames):
		while t_ai >= t_remove[f_remove]:
			timeline_append(-frames[f_remove])
			f_remove = f_remove + 1
			
		if t_af <= t_remove[f_remove]:
			timeline_append(size)
		else:
			s1 = round((t_remove[f_remove] - t_ai) * rate)
			timeline_append(s1)
			timeline_append(-frames[f_remove])
			f_remove = f_remove + 1
			timeline_append(size - s1)
	
	# Calculate maximum buffer size
	buffer_accumulation = list(accumulate(timeline))
	max_buffer_size = max(buffer_accumulation)
	
	# Return maximum buffer size
	return max_buffer_size


# Returns list of frame sizes and fps for input file
def get_frames(input_file):
	# Scan ffprobe data for frame rate and frame sizes
	# Note: ffprobe stores size data in bytes and we want it in bits hence the
	#		multiplication by 8
	command = [
		"ffprobe",
		"-loglevel", "quiet",
		"-select_streams", "v:0",
		"-show_entries", "stream=avg_frame_rate:packet=size",
		"-print_format", "json",
		input_file
	]
	media_info = json.loads(run(command, stdout=PIPE, stderr=DEVNULL).stdout)
	fps = float(Fraction(media_info["streams"][0]["avg_frame_rate"]))
	frames = [int(packet["size"]) * 8 for packet in media_info["packets"]]

	return frames, fps
    
if __name__ == "__main__":
	main()






















