#!/usr/bin/env python
#
# MZP Extractor version 1.0
# comes with ABSOLUTELY NO WARRANTY.
#
# Copyright (C) 2016 Hintay <hintay@me.com>
# Portions Copyright (C) 2016 Quibi
#
# MZP image files extraction utility
# For more information, see Specifications/mzp_format.md

from _extract_mzp_tiles import *
import struct
import os
import argparse

class ArchiveEntry:
	def __init__(self, sector_offset, offset, sector_size_upper_boundary, size, number_of_entries):
		self.sector_offset = sector_offset
		self.offset = offset
		self.sector_size_upper_boundary = sector_size_upper_boundary
		self.size = size
		self.real_size = (sector_size_upper_boundary - 1) // 0x20 * 0x10000 + size
		data_start_offset = 6 + 2 + number_of_entries * 8
		self.real_offset = data_start_offset + self.sector_offset * 0x800 + self.offset

#############################################################################
def parse_args():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('-b', '--bin',
		action='store_true', dest='bin',
		help='just extract MZP to bin and not output PNGs')
	parser.add_argument('-n', '--notmzx',
		action='store_true', dest='notmzx',
		help='do not extract MZX that extracted from MZP')
	parser.add_argument('input', metavar='input.mzp', help='input .mzp file')

	return parser, parser.parse_args()

#############################################################################
# extract verb #
################
def extract_verb(args):
	input_file_name = os.path.basename(args.input)
	input_file = open(input_file_name, 'rb')
	header = input_file.read(6)
	print('header: {0}'.format(header.decode('ASCII')))

	number_of_entries, = struct.unpack('<H', input_file.read(2))
	print('found {0} entries'.format(number_of_entries))

	entries_descriptors = []
	for i in range(number_of_entries):
		sector_offset, offset, sector_size_upper_boundary, size  = struct.unpack('<HHHH', input_file.read(8))
		entries_descriptors.append(ArchiveEntry(sector_offset = sector_offset, offset = offset, sector_size_upper_boundary = sector_size_upper_boundary, size = size, number_of_entries = number_of_entries))

	if(args.bin): extract_bin(input_file_name, input_file, entries_descriptors, args.notmzx)
	else: MzpFile(input_file_name, input_file, entries_descriptors)
	input_file.close()

def extract_bin(input_file_name, input_file, entries_descriptors, notmzx):
	output_dir = os.path.splitext(os.path.basename(input_file_name))[0] + '-unpacked'
	if not os.path.isdir(output_dir):
		os.mkdir(output_dir)

	for i in range(len(entries_descriptors)):
		input_file.seek(entries_descriptors[i].real_offset)
		data = input_file.read(entries_descriptors[i].real_size)

		# Desc
		if i == 0:
			desc_file_name = os.path.join(output_dir, '0desc.bin')
			write_file(data, desc_file_name)
			continue

		file_name = 'tile' + str(i)
		if notmzx:
			mzx_file_name = os.path.join(output_dir, file_name + '.mzx')
			write_file(data, mzx_file_name)
		else:
			extract_file_name = os.path.join(output_dir, file_name + '.ucp')
			input_file.seek(entries_descriptors[i].real_offset)
			sig, size = unpack('<LL', input_file.read(0x8))
			status, extract_data = mzx0_decompress(input_file, entries_descriptors[i].real_size-8, size)
			write_file(extract_data, extract_file_name)

def write_file(data, output_file_name):
	output_file = open(output_file_name, 'wb')
	output_file.write(data)
	output_file.close()

############
# __main__ #
############

if __name__ == '__main__':
	parser, args = parse_args()
	if (args.input != None): extract_verb(args)
	else:
		parser.print_usage()
		sys.exit(20)
	sys.exit(0)