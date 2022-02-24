#!/usr/bin/env python3

from argparse import ArgumentParser
import os
import json
import csv
import math
from subprocess import run, DEVNULL, PIPE
from fractions import Fraction
from itertools import accumulate
from multiprocessing import Pool

unit_base = 1000

def main():
	parser = ArgumentParser()
	parser.add_argument("file")
	parser.add_argument("--rate", type=float)				# Kilobits per second
	parser.add_argument("--buffer", type=float)			# kilobits
	parser.add_argument("--delay", type=float, default=5)		# seconds
	parser.add_argument("--fps", type=float)
	parser.add_argument("-v", "--verbose", action="store_true")
	args = parser.parse_args()
	
	# Variables
	file_open_method = 1
	delay_user = 0
	rate = 0
	buffer = 0
	
	# Checks existence of file
	if not os.path.isfile(args.file):
		exit(f"Error: File {args.file} does not exist")
		
	# Checks if file is CSV
	if args.file.endswith(".csv"):
		file_open_method = 2
	
	# Cannot have both rate and buffer
	if args.rate and args.buffer:
		exit("Error: Cannot input both rate and buffer. Pick one to calculate the other.")
	
	# Checks input rate and converts from kilobits/s to bits/s
	if args.rate:
		if args.rate > 0:
			rate = args.rate*unit_base
			args.plex = False
		else:
			exit(f"Error: Invalid rate {args.rate}. Must be greater than 0.")
	
	# Checks input buffer and converts from kilobits to bits
	if args.buffer:
		if args.buffer > 0:
			buffer = args.buffer*unit_base
			args.plex = False
		else:
			exit(f"Error: Invalid buffer {args.buffer}. Must be greater than 0.")
	
	# Check validity of delay argument
	if args.delay:
		if args.delay > 0:
			delay_user = args.delay
		else:
			exit(f"Error: Invalid delay {args.delay}. Delay must be greater than 0.")
	
	# Information for user
	print("Information: Reading file...")
	
	# Get list of frame sizes and fps from input file using method:
	#	1 = ffprobe
	#	2 = csv from x265
	frame_sizes, fps = get_frames(args.file, file_open_method)
		
	# Coarse check for valid input file
	if not len(frame_sizes) > 0:
		exit(f"Error: Input file {args.file} invalid")
	
	# Override frame rate detected by ffprobe with user input
	if args.fps and args.fps > 0:
		fps = args.fps
	if fps == 0:
		exit("Error: FPS needs to be specified for this file")
		
	# Pre-calculated values for convenience and/or speed
	number_frames = len(frame_sizes)
	
	# Information for user
	print(f"Information: Media has {number_frames} frames at {fps:.3f} frames per second.")

	# Decide to calculate rate or buffer
	if args.rate:
		# Information for user
		print("Information: Starting buffer size calculations...")
	
		max_buffer_size = calculate_buffer_size(frame_sizes, rate, delay_user, fps)
		if max_buffer_size is not None:
			print(f"Result: Maximum Buffer Size (b): {max_buffer_size:.0f}")
			print(f"Result: Maximum Buffer Size (MB): {max_buffer_size/(8*unit_base*unit_base):.2f}")
			exit()
		else:
			print(f"Result: Not possible to stream video at rate {rate/unit_base:.0f}kb/s with delay {delay_user:.2f}s")
			print("        Try increaseing rate or delay.")
		
	elif args.buffer:
		# Information for user
		print("Information: Starting rate value calculations...")

		rate = bisection_method(frame_sizes, fps, delay_user, buffer)
# 		rate = bisection_method_parallel(frame_sizes, fps, delay_user, buffer)
		print(f"Result: Minimum Rate (b/s): {rate:.3f}")
		print(f"Result: Minimum Rate (kb/s): {rate/unit_base:.3f}")
		exit()
		
	else:
		exit("Something has gone wrong!")


# Bisection Method - Returns minimum rate (float) in bits per second
def bisection_method(frames, fps, delay_user, buffer):
	accuracy = 1
	
	# Initial guesses for rate. a = lower limit, b = upper limit
	a = (sum(frames) / len(frames)) * fps
	b = max(frames) * fps
	
	# Loop and minimise f_c (make f_c as close to zero as possible)
	while (b - a) > accuracy:
		c = (a + b) * 0.5
		f_c = calculate_buffer_size(frames, c, delay_user, fps)
		if f_c is None:
			a = c
		else:
			if f_c - buffer > 0:
				a = c
			else:
				b = c

	# return the higher of the two bracketing values
	return b


# Bisection Method Parallel- Returns minimum rate (float) in bits per second
def bisection_method_parallel(frames, fps, delay_user, target):
	accuracy = 1
	num_cpu = os.cpu_count()
	
	# Initial guesses for rate. a = lower limit, b = upper limit
	a = (sum(frames) / len(frames)) * fps
	b = max(frames) * fps
	
	# Create pool
	p = Pool(maxtasksperchild=1)
	
	# Loop and minimise f_c (make f_c as close to zero as possible)
	while (b - a) > accuracy:
		cs = [a + (b-a) * (n/(num_cpu+1)) for n in range(1, num_cpu+1)]
		args = [(frames, c, delay_user, fps) for c in cs]
		buffers = p.starmap(calculate_buffer_size, args)
		
		for buffer, c in zip(buffers, cs):
			if buffer is None:
				a = c
				continue
			elif buffer - target > 0:
				a = c
			else:
				b = c
				break
	
	# Close pool
	p.close()
	
	# return the higher of the two bracketing values
	return b
	
	
# Returns max buffer size in bits (this will always be an integer value)
def calculate_buffer_size(frames, rate, delay_user, fps):
	# maximum download rate (maxrate) in bits per second
	delay_minimum = frames[0] / rate
	delay = max(delay_minimum, delay_user)

	# Create removal_time list
	t_remove = [delay + n/fps for n in range(len(frames))]

	# Two lists, initial arrival times and final arrival times
	t_arrive_i = [t - s/rate for t, s in zip(t_remove, frames)]
	t_arrive_f = t_remove.copy()
	
	# Adjust arrival time lists to eliminate any overlapping between frames
	for i in range(len(t_arrive_i)-1, 0, -1):
		if t_arrive_i[i] < t_arrive_f[i-1]:
			t_arrive_i[i-1] = t_arrive_i[i] - frames[i-1]/rate
			t_arrive_f[i-1] = t_arrive_i[i]
		else:
			t_arrive_i[i] = t_arrive_f[i-1]
	
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
def get_frames(input_file, method):
	if method == 1:
		# Scan ffprobe data for frame rate and frame sizes
		# Note: ffprobe provides two frame rate variables, r_frame_rate and
		#		avg_frame_rate. I am using avg_frame_rate because it is what Sam
		#		used and there might be an issue with r_frame_rate
		# Note: ffprobe stores size data in bytes and we want it in bits hence the
		#		multiplication by 8
		media_info = scan_media(input_file)
		fps = float(Fraction(media_info["streams"][0]["avg_frame_rate"]))
		frame_sizes = [int(packet["size"]) * 8 for packet in media_info["packets"]]
	elif method == 2:
		# Read data from CSV created by x265
		frame_sizes = []
		with open(input_file, "r") as f:
			reader = csv.reader(f)
			for line in reader:
				try:
					frame_sizes.append(int(line[4]))
				except:
					continue
		fps = 0
	else:
		exit(f"Error: Incorrect method {method}")
		
	return frame_sizes, fps
	
	
# Returns json-ified results from ffprobe for frame rate and packet size only
def scan_media(input_file):
	command = [
		"ffprobe",
		"-loglevel", "quiet",
		"-select_streams", "v:0",
		"-show_entries", "stream=r_frame_rate,avg_frame_rate:packet=size",
		"-print_format", "json",
		input_file
	]
	output = run(command, stdout=PIPE, stderr=DEVNULL).stdout
	return json.loads(output)
 
    
if __name__ == "__main__":
	main()






















