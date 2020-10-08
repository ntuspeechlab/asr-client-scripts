"""
Client module calling remote ASR 

@Updated: October 01, 2020

"""
__version__ = "1.0.0"
__author__  = "AISpeechlab - NTU"
__status__  = "Release"
__all__     = ['rate_limited', 'main']

import argparse
from ws4py.client.threadedclient import WebSocketClient
import time
import threading
import sys
import urllib.parse
import queue
import json
import time
import os
import datetime
import pyaudio

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms

import logging
# create logger
logger = logging.getLogger('client')
logger.setLevel(logging.DEBUG)

# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
logfh = logging.handlers.RotatingFileHandler('client.log', maxBytes=10485760, backupCount=10)
logfh.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter(u'%(levelname)8s %(asctime)s %(message)s ')
logging._defaultFormatter = logging.Formatter(u"%(message)s")

# add formatter to ch
ch.setFormatter(formatter)
logfh.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)
logger.addHandler(logfh)

def rate_limited(maxPerSecond):
    minInterval = 1.0 / float(maxPerSecond)
    def decorate(func):
        lastTimeCalled = [0.0]
        def rate_limited_function(*args,**kargs):
            elapsed = time.perf_counter() - lastTimeCalled[0]
            leftToWait = minInterval - elapsed
            if leftToWait>0:
                time.sleep(leftToWait)
            ret = func(*args,**kargs)
            lastTimeCalled[0] = time.perf_counter()
            return ret
        return rate_limited_function
    return decorate


class MyClient(WebSocketClient):

    def __init__(self, mode, audiofile, url, protocols=None, extensions=None, heartbeat_freq=None, byterate=32000,
                 save_adaptation_state_filename=None, send_adaptation_state_filename=None):
        super(MyClient, self).__init__(url, protocols, extensions, heartbeat_freq)
        self.final_hyps = []
        self.audiofile = audiofile
        self.byterate = byterate
        self.final_hyp_queue = queue.Queue()
        self.save_adaptation_state_filename = save_adaptation_state_filename
        self.send_adaptation_state_filename = send_adaptation_state_filename

        self.mode = mode
        self.audio = pyaudio.PyAudio()
        self.isStop = False

    @rate_limited(4)
    def send_data(self, data):
        self.send(data, binary=True)

    def opened(self):
        logger.info("Socket opened! " + self.__str__())

    def received_message(self, m):
        response = json.loads(str(m))
        def send_data_to_ws():
            if self.send_adaptation_state_filename is not None:
                logger.info("Sending adaptation state from %s" % self.send_adaptation_state_filename)
                try:
                    adaptation_state_props = json.load(open(self.send_adaptation_state_filename, "r"))
                    self.send(json.dumps(dict(adaptation_state=adaptation_state_props)))
                except:
                    e = sys.exc_info()[0]
                    logger.info("Failed to send adaptation state: %s" % e)

            logger.info("Start transcribing...")
            if self.mode == 'stream':
                stream = self.audio.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, input=True,
                    frames_per_buffer=CHUNK)
                while not self.isStop:
                    data = stream.read(int(self.byterate / 8), exception_on_overflow=False)
                    self.send_data(data) # send data

                stream.stop_stream()
                stream.close()
                self.audio.terminate()
            elif self.mode == 'file':
                with self.audiofile as audiostream:
                    for block in iter(lambda: audiostream.read(int(self.byterate/4)), ""):
                        self.send_data(block)
                        if len(block) == 0:
                            break

            logger.info("Audio sent, now sending EOS")
            self.send("EOS")
        if response['status'] == 0:
            if 'result' in response:
                trans = response['result']['hypotheses'][0]['transcript']
                if response['result']['final']:
                    #print >> sys.stderr, trans,
                    self.final_hyps.append(trans)

                    #print("\033[H\033[J") # clear console for better output
                    logger.info('%s' % trans)
                else:
                    print_trans = trans
                    if len(print_trans) > 80:
                        print_trans = "... %s" % print_trans[-76:]

                    #print("\033[H\033[J") # clear console for better output
                    logger.info('%s' % print_trans)
            if 'adaptation_state' in response:
                if self.save_adaptation_state_filename:
                    logger.info("Saving adaptation state to %s" % self.save_adaptation_state_filename)
                    with open(self.save_adaptation_state_filename, "w") as f:
                        f.write(json.dumps(response['adaptation_state']))
        else:
            logger.info("Received message from server (status %d)" % response['status'])
            if 'message' in response:
                logger.info("Message: %s" %  response['message'])
                if response['message'] == 'ready':
                    print('------------------------')
                    t = threading.Thread(target=send_data_to_ws)
                    t.start()


    def get_full_hyp(self, timeout=60):
        return self.final_hyp_queue.get(timeout)

    def closed(self, code, reason=None):
        print("Websocket closed() called")
        print(code)
        print(reason)
        #print >> sys.stderr
        self.final_hyp_queue.put(" ".join(self.final_hyps))


def main():

    parser = argparse.ArgumentParser(description='Command line client for kaldigstserver')
    parser.add_argument('-o', '--option', default="file", dest="mode", help="Mode of transcribing: audio file or streaming")
    parser.add_argument('-u', '--uri', default="ws://localhost:8888/client/ws/speech", dest="uri", help="Server websocket URI")
    parser.add_argument('-r', '--rate', default=32000, dest="rate", type=int, help="Rate in bytes/sec at which audio should be sent to the server. NB! For raw 16-bit audio it must be 2*samplerate!")
    parser.add_argument('-t', '--token', default="", dest="token", help="User token")
    parser.add_argument('-m', '--model', default=None, dest="model", help="model in azure container")
    parser.add_argument('--save-adaptation-state', help="Save adaptation state to file")
    parser.add_argument('--send-adaptation-state', help="Send adaptation state from file")
    parser.add_argument('--content-type', default='', help="Use the specified content type (empty by default, for raw files the default is  audio/x-raw, layout=(string)interleaved, rate=(int)<rate>, format=(string)S16LE, channels=(int)1")
    parser.add_argument('audiofile', nargs='?', help="Audio file to be sent to the server", type=argparse.FileType('rb'), default=sys.stdin)
    args = parser.parse_args()

    if args.mode == 'file' or args.mode == 'stream':
        content_type = args.content_type
        if content_type == '' and args.audiofile.name.endswith(".raw") or args.mode == 'stream':
            content_type = "audio/x-raw, layout=(string)interleaved, rate=(int)%d, format=(string)S16LE, channels=(int)1" %(args.rate/2)

        url = args.uri + '?%s' % (urllib.parse.urlencode([("content-type", content_type)])) + '&%s' % (urllib.parse.urlencode([("accessToken", args.token)])) + '&%s' % (urllib.parse.urlencode([("model", args.model)]))

        ws = MyClient(args.mode, args.audiofile, url, byterate=args.rate,
                    save_adaptation_state_filename=args.save_adaptation_state, send_adaptation_state_filename=args.send_adaptation_state)

        logger.info("\n URL: " + str(url) + "\n")

        ws.connect()
        result = ws.get_full_hyp()
        
        logger.info("\n------------------------\nFinal Result: \n")
        logger.info(result)
    else:
        print('\nTranscribe mode must be file or stream!\n')

if __name__ == "__main__":
    main()
