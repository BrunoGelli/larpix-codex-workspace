#!/usr/bin/env python3
"""
Simple PACMAN ping utility using larpix PACMAN message formatter.

Examples
--------
Ping one PACMAN endpoint:
    python scripts/pacman_ping.py --address 127.0.0.1 --port 5555

Ping repeatedly:
    python scripts/pacman_ping.py --address 127.0.0.1 --port 5555 --count 5 --interval 0.5
"""

import argparse
import time

import zmq

import larpix.format.pacman_msg_format as pacman_msg_format


def ping_once(socket, verbose=False):
    request = pacman_msg_format.format_msg('REQ', [('PING',)])
    if verbose:
        print('Send:', request.hex())
    socket.send(request)

    reply = socket.recv()
    if verbose:
        print('Reply:', reply.hex())

    header, words = pacman_msg_format.parse_msg(reply)

    is_pong = len(words) > 0 and words[0][0] == 'PONG'
    return is_pong, header, words


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--address', default='pacman-dev1.physics.ucdavis.edu', help='PACMAN server address (default: %(default)s)')
    parser.add_argument('--port', type=int, default=5555, help='PACMAN server REQ/REP port (default: %(default)s)')
    parser.add_argument('--timeout-ms', type=int, default=2000, help='ZMQ recv timeout in ms (default: %(default)s)')
    parser.add_argument('--count', type=int, default=1, help='Number of pings to send (default: %(default)s)')
    parser.add_argument('--interval', type=float, default=0.0, help='Delay between pings in seconds (default: %(default)s)')
    parser.add_argument('--verbose', action='store_true', help='Print raw message hex for TX/RX')
    args = parser.parse_args()

    endpoint = f"tcp://{args.address}:{args.port}"

    context = zmq.Context.instance()
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, args.timeout_ms)
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(endpoint)

    successes = 0
    failures = 0

    print(f'Connecting to {endpoint}')

    for i in range(args.count):
        try:
            ok, header, words = ping_once(socket, verbose=args.verbose)
            if ok:
                successes += 1
                print(f'[{i+1}/{args.count}] PING -> PONG | header={header} words={words}')
            else:
                failures += 1
                print(f'[{i+1}/{args.count}] Unexpected reply | header={header} words={words}')
        except zmq.error.Again:
            failures += 1
            print(f'[{i+1}/{args.count}] Timeout waiting for reply')
            # REQ socket requires recv before next send; recreate socket after timeout
            socket.close(0)
            socket = context.socket(zmq.REQ)
            socket.setsockopt(zmq.RCVTIMEO, args.timeout_ms)
            socket.setsockopt(zmq.LINGER, 0)
            socket.connect(endpoint)
        except Exception as exc:
            failures += 1
            print(f'[{i+1}/{args.count}] Error: {exc}')

        if i < args.count - 1 and args.interval > 0:
            time.sleep(args.interval)

    socket.close(0)

    print(f'Finished: {successes} success, {failures} failure')
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == '__main__':
    main()
