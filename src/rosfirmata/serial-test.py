import time
import signal
import os
from Queue import Queue
import serial
from serial.threaded import ReaderThread
from protocol import ProtocolConstants, ProtocolHandler

command_queue = Queue()
handler = ProtocolHandler(command_queue)

analog_values = dict()

def chk_proto_version(command, b):
    if b[1]!=ProtocolConstants.FIRMATA_PROTOCOL_MAJOR_VERSION \
      or b[2]!=ProtocolConstants.FIRMATA_PROTOCOL_MINOR_VERSION:
	print("Wrong protocol version: {0}.{1}".format(b[1], b[2]))

def chk_firmware_version(subcommand, b):
    # Ignore
    return

def handle_analog_msg(command, b):
    if len(b) == 3:
	pin = b[0] & 0xF
	value = b[2]<<7 | b[1]
	analog_values[pin] = value
	if pin == 0:
	    print("{0}: {1}".format(time.time(), value))

def handle_digital_msg(command, b):
    # Ignore
    print "digital"
    return

def handle_mapping_response(subcommand, b):
    print("Mapping response")

command_handler = dict()
sysex_command_handler = dict()

def set_command_handler(command, handler):
    command_handler[command] = handler

def set_sysex_command_handler(subcommand, handler):
    sysex_command_handler[subcommand] = handler

set_command_handler(ProtocolConstants.REPORT_VERSION, chk_proto_version)
set_command_handler(ProtocolConstants.ANALOG_MESSAGE, handle_analog_msg)
set_command_handler(ProtocolConstants.DIGITAL_MESSAGE, handle_digital_msg)
set_sysex_command_handler(ProtocolConstants.REPORT_FIRMWARE, chk_firmware_version)
set_sysex_command_handler(ProtocolConstants.ANALOG_MAPPING_RESPONSE, handle_mapping_response)

def get_handler():
    return handler

def processCommand(cmd):
    data = ["{0:x}".format(x) for x in cmd["data"]]
    if "subcommand" in cmd:
	has_handler = cmd["subcommand"] in sysex_command_handler
	if has_handler:
	    sysex_command_handler[cmd["subcommand"]](cmd["subcommand"], cmd["data"])
	else:
	    print("SYSEX {0:x} {1} {2}".format(cmd["subcommand"], has_handler, data))
    else:
	has_handler = cmd["command"] in command_handler
	if has_handler:
	    command_handler[cmd["command"]](cmd["command"], cmd["data"])
	else:
	    print("{0:x} {1} {2}".format(cmd["command"], has_handler, data))

ser = serial.Serial("/dev/ttyAMA0", 115200)

reader = ReaderThread(ser, get_handler)
reader.start()

def signal_handler(sig, frame):
    print('You pressed Ctrl+C')
    ser.close()
    os._exit(0)
		    
signal.signal(signal.SIGINT, signal_handler)
		    
def reset_queue():
    while not(command_queue.empty()):
	command_queue.get_nowait()

def send_sysex(bytes):
    reader.write(chr(0xF0))
    for b in bytes:
	reader.write(chr(b))
    reader.write(chr(0xF7))

def system_reset():
    reader.write(b'\xFF')

def set_sampling_interval(interval):
    send_sysex([0x7A, interval&0x7F, (interval >> 7) & 0x7F])

def request_analog_mapping():
    reader.write(b'\xF0\x69\xF7');

def request_analog_reporting(pin):
    reader.write(chr(0xC0 | (pin & 0x0F)))
    reader.write(chr(1))

def send_sync():
    system_reset()
    set_sampling_interval(500)
    request_analog_mapping()

# Synchronize
start = time.clock()
in_sync = False
print("Sending synch... {0}".format(time.clock()))
reset_queue()
send_sync()
last_query = start
while not(in_sync) and time.clock()-start < 20.0:
    t = time.clock()
    if t - last_query > 0.1:
	reset_queue()
	send_sync()
	print("Sending synch... {0}".format(t))
	last_query = t
    try:
	#print("Waiting for response {0}".format(t))
	while not(command_queue.empty()):
	    c = command_queue.get_nowait()
	    #print("Got command {0}".format(time.clock()))
	    if ("subcommand" in c) and c["subcommand"]==ProtocolConstants.ANALOG_MAPPING_RESPONSE:
		in_sync = True
		print("Synch! {0}".format(t))
		request_analog_reporting(0)
    except:
	print("Timeout {0}".format(t))
	reset_queue()
	send_sync()

while True:
    try:
	c = command_queue.get(True, 2)
	processCommand(c)
    except:
	print "Timeout"
