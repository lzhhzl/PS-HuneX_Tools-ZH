import os, sys
from struct import unpack, pack
from subprocess import call
import glob
import zlib
from mzx.decomp_mzx0 import mzx0_decompress

# http://blog.flip-edesign.com/?p=23
class Byte(object):
	def __init__(self, number):
		self.number = number

	@property
	def high(self):
		return self.number >> 4

	@property
	def low(self):
		return self.number & 0x0F


def write_pngsig(f):
	f.write(b'\x89\x50\x4E\x47\x0D\x0A\x1A\x0A')

def write_pngchunk_withcrc(f, type, data):
	f.write(pack(">I",len(data)))
	f.write(type)
	f.write(data)
	f.write(pack(">I",zlib.crc32(type+data, 0)& 0xffffffff))


"""
   color = 1 (palette used), 2 (color used), and 4 (alpha channel used). Valid values are 0, 2, 3, 4, and 6. 
 
   Color	Allowed	Interpretation
   Type	Bit Depths
   
   0	   1,2,4,8,16  Each pixel is a grayscale sample.
   
   2	   8,16		Each pixel is an R,G,B triple.
   
   3	   1,2,4,8	 Each pixel is a palette index;
					   a PLTE chunk must appear.
   
   4	   8,16		Each pixel is a grayscale sample,
					   followed by an alpha sample.
   
   6	   8,16		Each pixel is an R,G,B triple,
					   followed by an alpha sample.
"""
def write_ihdr(f, width, height, depth, color):
	chunk = pack(">IIBB",width,height,depth,color) + b'\0\0\0'
	write_pngchunk_withcrc(f, b"IHDR", chunk)

def write_plte(f, palettebin):
	write_pngchunk_withcrc(f, b"PLTE", palettebin)

def write_trns(f, transparencydata):
	write_pngchunk_withcrc(f, b"tRNS", transparencydata)

def write_idat(f, pixels):
	write_pngchunk_withcrc(f, b"IDAT", zlib.compress(pixels))

def write_iend(f):
	write_pngchunk_withcrc(f, b"IEND", b"")

def chunks(l, n):
	""" Yield successive n-sized chunks from l.
	"""
	for i in range(0, len(l), n):
		yield l[i:i+n]

###############################################
# struct TGAHeader
# {
#   uint8   idLength,		   // Length of optional identification sequence.
#		   paletteType,		// Is a palette present? (1=yes)
#		   imageType;		  // Image data type (0=none, 1=indexed, 2=rgb,
#							   // 3=grey, +8=rle packed).
#   uint16  firstPaletteEntry,  // First palette index, if present.
#		   numPaletteEntries;  // Number of palette entries, if present.
#   uint8   paletteBits;		// Number of bits per palette entry.
#   uint16  x,				  // Horiz. pixel coord. of lower left of image.
#		   y,				  // Vert. pixel coord. of lower left of image.
#		   width,			  // Image width in pixels.
#		   height;			 // Image height in pixels.
#   uint8   depth,			  // Image color depth (bits per pixel).
#		   descriptor;		 // Image attribute flags.
# };

def is_indexed_bitmap(bmpinfo):
	return bmpinfo == 0x01

class MzpFile:
	def __init__(self, filename, data, entries_descriptors):
		self.filename = filename
		self.basename = os.path.splitext(filename)[0]
		self.data = data
		self.entries_descriptors = entries_descriptors
		self.paletteblob = b''
		self.palettepng = b''
		self.transpng = b''
		self.extract_desc()
		self.rows = [b''] * self.height
		self.loop_data()
		self.output_png()

	def loop_data(self):
		for y in range(self.tile_y_count):
			startrownum = y * self.tile_height
			rowcount = min(self.height, startrownum + self.tile_height) - startrownum
			self.loop_x(startrownum, rowcount)

	def loop_x(self, startrownum, rowcount):
		for x in range(self.tile_x_count):
			#print("copy {}rows at {},{}".format(rowcount, x * self.tile_width, startrownum))
			#sys.exit(0)
			entry = self.entries_descriptors.pop(0)
			self.data.seek(entry.real_offset)
			sig, size = unpack('<LL', self.data.read(0x8))
			status, decbuf = mzx0_decompress(self.data, entry.real_size-8, size)
			if self.bitmapbpp == 4:
				tiledata = b''
				for octet in decbuf:
					thebyte = Byte(octet)
					tiledata += pack('BB', thebyte.high, thebyte.low)
				decbuf = tiledata
			self.rowsmzx = list(chunks(decbuf, self.tile_width))

			for i, tilerow_rawpixels in enumerate(chunks(decbuf, self.tile_width * self.bitmapbpp // 8)):
				if i >= rowcount:
					break
				curwidth = len(self.rows[startrownum + i])
				pxcount = min(self.width, curwidth + self.tile_width) - curwidth
				try:
					self.rows[startrownum + i] += tilerow_rawpixels[:pxcount]
				except(IndexError):
					print(startrownum + i)

	def extract_desc(self):
		self.data.seek(self.entries_descriptors[0].real_offset)
		self.width, self.height, self.tile_width, self.tile_height, self.tile_x_count, self.tile_y_count, self.bmp_type, self.bmp_depth = unpack('<HHHHHHHH', self.data.read(0x10))
		if self.bmp_type not in [0x01, 0x03]:
			print("Unknown type 0x{:02X}".format(self.bmp_type))
			call(["cmd", "/c", "pause"])
			sys.exit(1)
		if is_indexed_bitmap(self.bmp_type):
			if self.bmp_depth == 0x01:
				self.bitmapbpp	=	8
				self.palettecount = 0x100
			elif self.bmp_depth == 0x00 or self.bmp_depth == 0x10:
				self.bitmapbpp	=	4
				self.palettecount = 0x10
			elif self.bmp_depth == 0x11 or self.bmp_depth == 0x91: # experimental
				self.bitmapbpp	=	8
				self.palettecount = 0x100
			else:
				print("Unknown depth 0x{:02X}".format(self.bmp_depth))
				call(["cmd", "/c", "pause"])
				sys.exit(1)

			if self.bmp_depth in [0x00, 0x01, 0x10]:
				for i in range(self.palettecount):
					r = self.data.read(1)
					g = self.data.read(1)
					b = self.data.read(1)
					a = self.data.read(1)
					self.paletteblob += (b + g + r + a)
					self.palettepng += (r + g + b)
					self.transpng += a
			elif self.bmp_depth in [0x11, 0x91]:
				# PalType:RGBATim2:
				# Author: caoyang131
				pal_start = self.data.tell()
				for h in range(0,self.palettecount*4//0x80,1):
					for i in range(2):
						for j in range(2):
							self.data.seek(h*0x80+(i+j*2)*0x20+pal_start)
							for k in range(8):
								r = self.data.read(1)
								g = self.data.read(1)
								b = self.data.read(1)

								# Experimental 128阶透明度转换
								# Author: Hintay <hintay@me.com>
								temp_a, = unpack('B', self.data.read(1))
								a = (temp_a << 1) + (temp_a >> 6) if(temp_a < 0x80) else 255
								a = pack('B', a)

								self.paletteblob += (b + g + r + a)
								self.palettepng += (r + g + b)
								self.transpng += a
			else:
				print("Unsupported palette type 0x{:02X}".format(self.bmp_depth))
				call(["cmd", "/c", "pause"])
				sys.exit(1)

			# 补全索引
			for i in range(self.palettecount, 0x100):
				self.paletteblob += b'\x00\x00\x00\xFF'
				self.palettepng += b'\x00\x00\x00'
				self.transpng += b'\xFF'

		elif bmp_type == 0x03:  # 'PEH' 8bpp + palette
			print("Unsupported type 0x{:02X} (PEH)".format(self.bmp_type))
			call(["cmd", "/c", "pause"])
			sys.exit(1)

		del self.entries_descriptors[0]

	# 输出PNG
	def output_png(self):
		pngoutpath = "{}.png".format(self.basename)
		with open(pngoutpath, 'wb') as pngout:
			write_pngsig(pngout)
			if is_indexed_bitmap(self.bmp_type):
				write_ihdr(pngout, self.width, self.height, 8, 3)  # 8bpp (PLTE)
				write_plte(pngout, self.palettepng)
				write_trns(pngout, self.transpng)

			elif self.bmp_type == 0x03:  # ABGR truecolor
				write_ihdr(pngout, self.width, self.height, 8, 6)  # 32bpp

			# split into rows and add png filtering info (mandatory even with no filter)
			rowdata = b''
			for row in self.rows:
				rowdata += b'\x00' + row

			write_idat(pngout, rowdata)
			write_iend(pngout)
		#call(["cmd", "/c", "start", pngoutpath])

""" Commented out: output each tile individually (tga/png)
	###
	for infilepath in glob.iglob("*.out"):
		print(infilepath)
		outfilepath = outfilepattern.format(infilepath)
		with open(outfilepath, 'wb') as outfile:
			outfile.write(b"\x00\x01\x01\x00\x00" + pack("<H", 0x100) + b"\x20\x00\x00\x00\x00" + pack('<HHBB', tile_width, tile_height, 8, 0x20|8))
			outfile.write( paletteblob )
			data = open(infilepath,'rb').read()
			if len(data) < tile_width * tile_height * bitmapbpp // 8:
				print("Not enough data: {} {}".format(len(data), tile_width * tile_height * bitmapbpp // 8))
			if bitmapbpp == 8:
				outfile.write( data )
			elif bitmapbpp == 4:
				for octet in data:
					thebyte = Byte(octet)
					imagedata += pack('BB', thebyte.high, thebyte.low)
				data = imagedata
				outfile.write( data )

		# uses from just above loop: data
		with open("ztile{}.png".format(infilepath), 'wb') as pngout:
			write_pngsig(pngout)
			write_ihdr(pngout, tile_width, tile_height, 8, 3)  # 8bpp (PLTE)
			write_plte(pngout, palettepng)
			write_trns(pngout, transpng)

			# split into rows and add png filtering info (mandatory even with no filter)
			rowdata = b''
			for i, rowrawpixels in enumerate(chunks(data, tile_width)):
				rowdata += b'\x00' + rowrawpixels
			
			write_idat(pngout, rowdata)
			write_iend(pngout)

		#call(["cmd", "/c", "start", outfilepath])
"""