"""
Client module calling remote ASR 

@Updated: October 01, 2020
@Maintain by: Ly

"""

import os, time
import sys
import json
import requests
import subprocess
import shutil
import urllib.request


__version__ = "1.0.0"
__author__  = "AISpeechlab - NTU"
__status__  = "Release"
__all__     = ['get_audio_length', 'send_audio', 'check_status', 'get_transcription']


_SPEECH_URL = 'https://gateway.speechlab.sg'
_KEY = 'Bearer YOUR_TOKEN_HERE'
_HEADER = {'accept': 'application/json', 'Authorization': _KEY}
_QUEUE = 'normal'
_LANGUAGE = "english"


def get_audio_length(audiofile):
    ''' Check the audio length of input audio '''
    # cmd: ffmpeg -i file.mkv 2>&1 | grep -o -P "(?<=Duration: ).*?(?=,)"
    p1 = subprocess.Popen(['ffmpeg',  '-i', audiofile], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    p2 = subprocess.Popen(["grep",  "-o", "-P", "(?<=Duration: ).*?(?=,)"], stdin=p1.stdout, stdout=subprocess.PIPE)
    p1.stdout.close()
    
    print("The audio file length in hh:mm::ss format: " + p2.communicate()[0].decode("utf-8").strip())
    
    cmd = 'ffprobe -i {} -show_entries format=duration -v quiet -of csv="p=0"'.format(audiofile)
    output = subprocess.check_output(
        cmd,
        shell=True, # Let this run in the shell
        stderr=subprocess.STDOUT
    )
    # return round(float(output))  # ugly, but rounds your seconds up or down
    print("The audio file length in seconds: " + str(float(output)))
    return float(output)
    

def check_status(speech_id):
    ''' Check ASR status with given id '''
    try:
        url = _SPEECH_URL + '/speech/' + speech_id
        res = requests.get(url, headers=_HEADER)
        res = res.json()
        cur_status = res['status']
        print("... Current status: " + cur_status)
        return cur_status
        
    except Exception as ex:
        print('... Error in getting ASR status: ', str(ex))


def download_trans(speech_id):
    try:
        url = _SPEECH_URL + '/speech/' + speech_id + '/result'
        res = requests.get(url, headers=_HEADER)
        result_link = res.json()['url']
        print("... Download link: " + result_link)
        
        with urllib.request.urlopen(result_link) as response, open(speech_id + '.zip', 'wb') as out_file:
           content_length = int(response.getheader('Content-Length'))
           shutil.copyfileobj(response, out_file)
           print(f"... File saved. {content_length:,} bytes.")
        
        return res.ok
    except Exception as ex:
        print('... Error in getting ASR status: ', str(ex))


def send_audio(audio_file):
    ''' Send an audio file to remote ASR server '''
    try:
        url = _SPEECH_URL + '/speech'
        files = {
                'file':  open(audio_file, 'rb'),
        }
        data = {
              'lang': _LANGUAGE,
              'queue': _QUEUE # this is important, you must parse correct queue for your account here
        }
        
        res = requests.post(url, files=files, data=data, headers=_HEADER)
        res = res.json()
        
        speech_id=None
        if ('statusCode' in res and res['statusCode'] == 404):
            print('... Error in submitting audio(s): ', str(res), '. \nPlease check your token again.')

        elif ('statusCode' in res and res['statusCode'] == 403):
            print('... Error in submitting audio(s): ', str(res), '. \nPlease change your queue information.')

        else: 
            speech_id = res['_id']
        return speech_id
        
    except Exception as ex:
        print('... Exception in submitting audio(s): ', str(ex))


def main(audiofile):
    
    audio_length_in_seconds = get_audio_length(audiofile)
    _time_delay = max(60.0, audio_length_in_seconds) # The lowest boundary is 1min. 
    
    speech_id = send_audio(audiofile)
    print('... Getting speech id %s ...' % speech_id)
    if (speech_id == None):
        sys.exit("*** You don't have a speech id to process.")
    
    
    completed = False
    _MAX_TRY = 10
    i = 0
    while (completed != "done") and i < _MAX_TRY:
        time.sleep(_time_delay)
        i += 1
        print('... %02d waiting ASR result ...' % i)
        completed = check_status(speech_id)

    if (completed != "done"):
        print('*** Error: ASR did not complete the transcription')
    else:
        print('*** ASR done!')
        print('... Downloading transcription ...')
        download_trans(speech_id)
        print('*** Finish downloading transcription!')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Please input your audio file")
        print("Usage: python asr_transcribe_batch.py <inputaudiofile> ")
    else:
        main(sys.argv[1])









#
