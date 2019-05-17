"""
Media Player component to integrate TVs exposing the Joint Space API.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/media_player.philips_js/
"""

"""Philips TV"""
import logging
from datetime import timedelta
#from datetime import timedelta, datetime

import requests
import json
import sys
import subprocess
import voluptuous as vol

from homeassistant.components.media_player import (MediaPlayerDevice, PLATFORM_SCHEMA)
from homeassistant.components.media_player.const import (SUPPORT_NEXT_TRACK, SUPPORT_PAUSE, SUPPORT_PREVIOUS_TRACK,
  SUPPORT_SELECT_SOURCE, SUPPORT_TURN_OFF, SUPPORT_TURN_ON,
  SUPPORT_VOLUME_MUTE, SUPPORT_VOLUME_STEP, SUPPORT_PLAY, MEDIA_TYPE_CHANNEL)

from homeassistant.const import (
  CONF_HOST, CONF_NAME, STATE_OFF, STATE_ON, STATE_UNKNOWN, CONF_PORT)

import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

CONF_TIMEOUT = 'timeout'

DEFAULT_NAME = 'Philips TV'
DEFAULT_PORT = 1925
DEFAULT_TIMEOUT = 0

BASE_URL = 'http://{0}:{1}/1/{2}'
CONNECTION_FAIL_COUNT = 5
CONNECTION_TIMEOUT = 5.0

SUPPORT_PHILIPSTV = SUPPORT_NEXT_TRACK | SUPPORT_PAUSE | SUPPORT_PREVIOUS_TRACK | \
                    SUPPORT_SELECT_SOURCE | SUPPORT_TURN_OFF |  SUPPORT_VOLUME_MUTE | \
                    SUPPORT_VOLUME_STEP | SUPPORT_PLAY

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
  vol.Required(CONF_HOST): cv.string,
  vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
  vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
  vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
})

def setup_platform(hass, config, add_devices, discovery_info=None):
  """Set up the Philips TV platform."""
  
  if config.get(CONF_HOST) is not None:
    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT)
    name = config.get(CONF_NAME)
    timeout = config.get(CONF_TIMEOUT)
  else:
    _LOGGER.warning('Cannot determine device')
    return
  
  add_devices([PhilipsTVDevice(host, port, name, timeout)])
  _LOGGER.info("Philips TV %s:%d added as '%s'", host, port, name)

class PhilipsTVDevice(MediaPlayerDevice):
  """Representation of a Philips TV."""
  
  def __init__(self, host, port, name, timeout):
    """Initialize the Philips device."""
    
    self._host = host
    self._port = port
    self._name = name
    self._timeout = timeout
    
    self._channel_name = None
    self._connectionfailure = 0
    self._muted = False
    self._playing = True
    self._source = None
    self._source_id = None
    self._source_list = []
    self._source_mapping = {}
    self._state = STATE_UNKNOWN
    self._volume = None
    self._volume_max = None
    self._volume_min = None
    self._watching_tv = False
    
  def update(self):
    """Update state of device."""
    if sys.platform == 'win32':
      _ping_cmd = ['ping', '-n 1', '-w', '1000', self._host]
    else:
      _ping_cmd = ['ping', '-n', '-q', '-c1', '-W1', self._host]
      
    ping = subprocess.Popen(_ping_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
      ping.communicate()
      if ping.returncode == 0:
        self._state = STATE_ON
      else:
        self._state = STATE_OFF
    except subprocess.CalledProcessError:
      self._state = STATE_OFF
    
    if self._state == STATE_ON:
      self.get_audio_data()
      self.get_sources()
      self.get_current_source()
      self.get_current_channel()
    else:
       self._channel_name = None
       self._connectionfailure = 0
       self._muted = False
       self._playing = False
       self._source = None
       self._source_list = []
       self._source_mapping = {}
       self._volume = None
       self._volume_max = None
       self._volume_min = None
  
  @property
  def name(self):
    """Return the device name."""
    return self._name
  
  @property
  def state(self):
    """Return the state of the device."""
    return self._state
  
  @property
  def supported_features(self):
    """Flag media player features that are supported."""
    # TODO: Source control and TV control etc.
    return SUPPORT_PHILIPSTV
  
  @property
  def source(self):
    """Return the current input source."""
    return self._source
  
  @property
  def source_list(self):
    """List of available input sources."""
    return self._source_list
  
  def select_source(self, source):
    """Set the input source."""
    if source in self._source_mapping:
      self._source_id = self._source_mapping.get(source)
      if self.post_json_request('sources/current', {'id': self._source_id}):
        self._source = source
        self._watching_tv = bool(self._source_id == '11')
  
  @property
  def is_volume_muted(self):
    """Boolean if volume is currently muted."""
    return self._muted
  
  @property
  def volume_level(self):
    """Volume level of the media player (0..1)."""
    return self._volume
  
  @property
  def media_channel(self):
    """Channel currently playing."""
    return self._channel_name
    
  @property
  def media_content_id(self):
    """Content ID of current playing media."""
    return self._channel_name
  
  @property
  def media_title(self):
    """Title of current playing media."""
    media_title = '{}'.format(self._source)
    if self._watching_tv and self._channel_name:
      media_title = '{} - {}'.format(self._source, self._channel_name)
    
    return media_title
  
  @property
  def media_content_type(self):
    """Content type of current playing media."""
    return MEDIA_TYPE_CHANNEL
  
  def get_json_request(self, path):
    """Get JSON Request from TV."""
    try:
      if self._connectionfailure:
        self._connectionfailure -= 1
        return None
      response = requests.get(BASE_URL.format(self._host, self._port, path), timeout=CONNECTION_TIMEOUT)
      return json.loads(response.text)
    except requests.exceptions.RequestException as error:
      _LOGGER.debug('Exception: %s', str(error))
      self._connectionfailure = CONNECTION_FAIL_COUNT
      return None
  
  def post_json_request(self, path, data):
    """Post JSON Request to TV."""
    try:
      if self._connectionfailure:
        self._connectionfailure -= 1
        return False
      response = requests.post(BASE_URL.format(self._host, self._port, path), data=json.dumps(data), timeout=CONNECTION_TIMEOUT)
      if response.status_code == 200:
        return True
      else:
        return False
    except requests.exceptions.RequestException as error:
      _LOGGER.debug('Exception: %s', str(error))
      self._connectionfailure = CONNECTION_FAIL_COUNT
      return False
  
  # Channel functions
  def get_current_channel(self):
    """Retrieve the current channel."""
    channels = None
    channel_id = None
    
    if self._state == STATE_OFF or self._state == STATE_UNKNOWN:
      return
    
    # Get channels
    data = self.get_json_request('channels')
    if data:
      channels = data
    
    data = self.get_json_request('channels/current')
    if data:
      channel_id = data['id']
    
    if channels and channel_id in channels:
      self._channel_name = channels[channel_id]['name']
  
  # Media functions.
  
  def media_play_pause(self):
    """Simulate play pause media player."""
    if self._watching_tv:
      return
    
    if self._playing:
      self.media_pause()
    else:
      self.media_play()
  
  def media_play(self):
    """Send play command."""
    if self._watching_tv:
      return
    
    result = self.send_key('PlayPause')
    if result:
      self._playing = True
  
  def media_pause(self):
    """Send media pause command to media player."""
    if self._watching_tv:
      return
    
    result = self.send_key('Pause')
    if result:
      self._playing = False
  
  def media_next_track(self):
    """Send next track command."""
    if self._watching_tv:
      result = self.send_key('ChannelStepUp')
      if result:
        self.get_current_channel()
    else:
      self.send_key('Next')
  
  def media_previous_track(self):
    """Send the previous track command."""
    if self._watching_tv:
      result = self.send_key('ChannelStepDown')
      if result:
        self.get_current_channel()
    else:
      self.send_key('Previous')
  
  # Source functions
  def get_current_source(self):
    """Get the current source."""
    if self._state == STATE_OFF or self._state == STATE_UNKNOWN:
      return
    
    if self._source_list:
      data = self.get_json_request('sources/current')
      if data:
        self._source_id = data['id']
        self._watching_tv = bool(self._source_id == '11')
        if self._source_mapping:
          try:
            for name, value in self._source_mapping.items():
              if value == self._source_id:
                self._source = name
          except:
            self._source = None
        else:
          self._source = None
      else:
        self._source = None
    else:
      self._source = None
  
  def get_sources(self):
    """Retrieve the sources."""
    if self._state == STATE_OFF or self._state == STATE_UNKNOWN:
      return
    
    if not self._source_list:
      data = self.get_json_request('sources')
      if data:
        for sourceid in sorted(data):
          sourcename = data.get(sourceid, dict()).get('name', None)
          self._source_list.append(sourcename)
          self._source_mapping[sourcename] = sourceid
  
  # Volume functions
  def get_audio_data(self):
    """Retrieve the audio data."""
    if self._state == STATE_OFF or self._state == STATE_UNKNOWN:
      return
    
    audiodata = self.get_json_request('audio/volume')
    if audiodata:
      self._volume_max = int(audiodata['max'])
      self._volume_min = int(audiodata['min'])
      self._volume = int(audiodata['current'])
      self._muted = audiodata['muted']
    else:
      self._volume_max = None
      self._volume_min = None
      self._volume = None
      self._muted = False
  
  def volume_up(self):
    """Send volume up command."""
    result = self.send_key('VolumeUp')
    if result:
      self.get_audio_data()
  
  def volume_down(self):
    """Send volume down command."""
    result = self.send_key('VolumeDown')
    if result:
      self.get_audio_data()
  
  def mute_volume(self, muted):
    """Send mute command."""
    result = self.send_key('Mute')
    if result:
      self._muted = muted
  
  # Other functions
  def turn_off(self):
    """Turn off media player."""
    self.send_key('Standby')
  
  def send_key(self, key):
    """Send key command."""
    if self._state == STATE_OFF or self._state == STATE_UNKNOWN:
      return False
    return self.post_json_request('input/key', {'key': key})
