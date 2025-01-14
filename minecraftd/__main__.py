#!/usr/bin/env python3
import sys
import logging
import signal
import os
from .lineprocessor import LineProcessor
from .process import Process
from .controlsocket import ControlSocket
from .sessionclient import SessionClient
from .config import ProgramConfig, ServerConfig

CONFIG_FILE="/etc/minecraftd.json" # default

def runDaemon(program_cfg, server_cfg):
	logging.basicConfig(filename=program_cfg.logFilePath(), level=program_cfg.logLevel(), format="%(asctime)s - %(levelname)s: %(message)s")
	logging.info("Minecraftd is starting...")

	try:
		cs = ControlSocket(server_cfg.socketPath())

	except FileNotFoundError:
		logging.critical("Failed to create socket: Path not found")
		return 1

	except PermissionError:
		logging.critical("Failed to create socket: Permission denied")
		return 1

	try:
		pr = Process(server_cfg.compileCommand(),server_cfg.cwd()) # starts the process

	except FileNotFoundError as e:
		logging.critical("Failed to start process: {}".format(str(e)))
		return 1

	lp = LineProcessor(pr,cs,program_cfg.historyLen())
	lp.start()

	# and now the ugly part:
	while True:
		try:
			for l in pr.getStdout(): # Okay this miiiiiight not be the best way to do this... We could merge it into the socket's select, and make the whole program single threaded... I just couldn't think of a nicer way to separate this
				lp.passLine(l.decode('utf-8')) # line processor expects strings

			break # stdout reading ended without exceptions

		except KeyboardInterrupt: # SIGINT sends a "stop" command to the server, and it will shutdown greacefully (using Popen.wait to wait for termination would end up in deadlock, because we use stdin/stdout instead of communicate)
			signal.signal(signal.SIGINT, signal.SIG_IGN) # ignore any further sigint, because the shutdown process is already started
			logging.info("Stopping minecraft server...")
			lp.passLine("Minecraftd: Daemon is shuttig down! Stopping minecraft server...\n")
			pr.sendCommandList(server_cfg.shutdownCommands()) # should contain "stop"


	signal.signal(signal.SIGINT, signal.SIG_IGN) # we are shutting down, so signals are ignored

	logging.info("Minecraftd is shutting down...")
	lp.shutdown() # stops the thread and disconnects the user
	lp.join() # wait for line processor to close, before closing the control socket
	cs.close()

	return pr.getReturnCode()


def attachSession(server_cfg):

	try:
		sc = SessionClient(server_cfg.socketPath())

	except (ConnectionRefusedError,FileNotFoundError):
		print("Couldn't connect to Minecraftd console (is the daemon running?)")
		return

	except PermissionError:
		print("You have no permission to attach to Minecraftd console")
		return

	try:
		sc.run()

	except KeyboardInterrupt:
		sc.close()

	print("Session closed")


def main():

	server_name = sys.argv[-1]
	if server_name == __file__ or server_name == '--daemon' or 'bin/minecraftd' in server_name:
		print("CRITICAL: Must supply a server name!")
		sys.exit(1)

	try:
		config_file_to_load = os.environ['MINECRAFTD_CONFIG']
	except KeyError: # environment variable is not set
		config_file_to_load = CONFIG_FILE

	try:
		program_cfg = ProgramConfig(config_file_to_load)
		server_cfg = ServerConfig(program_cfg.servers()[server_name])

	except Exception as e:
		print("CRITICAL: Failed to load config file: {}".format(str(e)))
		sys.exit(1)

	if '--daemon' in sys.argv: # start daemon

		rc = runDaemon(program_cfg,server_cfg)
		sys.exit(rc) # the return code of minecraftd daemon is the return code of the minecraft server

	else: # attach screen

		attachSession(server_cfg)


if __name__ == '__main__':
	main()
