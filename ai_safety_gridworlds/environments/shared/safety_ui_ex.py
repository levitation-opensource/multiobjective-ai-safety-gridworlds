# Copyright 2022 Roland Pihlakas. https://github.com/levitation-opensource/multiobjective-ai-safety-gridworlds
# Copyright 2018 The AI Safety Gridworlds Authors. All Rights Reserved.
# Copyright 2017 the pycolab Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or  implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Frontends for humans who want to play pycolab games."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import curses
import datetime

from ai_safety_gridworlds.environments.shared.mo_reward import mo_reward
from ai_safety_gridworlds.environments.shared.ma_reward import ma_reward
from ai_safety_gridworlds.environments.shared.safety_game_moma import AGENT_SPRITE
from ai_safety_gridworlds.environments.shared import safety_game
from ai_safety_gridworlds.environments.shared import safety_game_mo
from ai_safety_gridworlds.environments.shared import safety_game_moma
from ai_safety_gridworlds.environments.shared import safety_ui

import numpy as np

from pycolab.human_ui import _format_timedelta
from pycolab.protocols import logging as plab_logging

import six


# adapted from ai_safety_gridworlds\environments\shared\safety_ui.py
class SafetyCursesUiEx(safety_ui.SafetyCursesUi):
  """A terminal-based UI for pycolab games.

  This is deriving from pycolab's `human_ui.CursesUi` class and shares a
  lot of its code. The main purpose of having a separate class is that we want
  to use the `play()` method on an instance of `SafetyEnvironment` and not just
  a pycolab game `Engine`. This way we can store information across
  episodes, conveniently call `get_overall_performance()` after the human has
  finished playing. It is also ensuring that human and agent interact with the
  environment in the same way (e.g. if `SafetyEnvironment` gets derived).
  """

  #def __init__(self, 
  #             *args, 
  #             agent_perspectives=None,
  #             **kwargs):   # ADDED
    
  #  self._agent_perspectives = agent_perspectives

  #  super(SafetyCursesUiEx, self).__init__(*args, **kwargs)


  # adapted from SafetyCursesUi._init_curses_and_play(self, screen) in ai_safety_gridworlds\environments\shared\safety_ui.py
  def _init_curses_and_play(self, screen):
    """Set up an already-running curses; do interaction loop.

    This method is intended to be passed as an argument to `curses.wrapper`,
    so its only argument is the main, full-screen curses window.

    Args:
      screen: the main, full-screen curses window.

    Raises:
      ValueError: if any key in the `keys_to_actions` dict supplied to the
          constructor has already been reserved for use by `CursesUi`.
    """
    # This needs to be overwritten to use `self._env.step()` instead of
    # `self._game.play()`.

    # See whether the user is using any reserved keys. This check ought to be in
    # the constructor, but it can't run until curses is actually initialised, so
    # it's here instead.
    for key, action in six.iteritems(self._keycodes_to_actions):
      if key in (curses.KEY_PPAGE, curses.KEY_NPAGE):
        raise ValueError(
            'the keys_to_actions argument to the CursesUi constructor binds '
            'action {} to the {} key, which is reserved for CursesUi. Please '
            'choose a different key for this action.'.format(
                repr(action), repr(curses.keyname(key))))

    self.map_row_offset = 3   # ADDED

    # TODO: config or auto-calculate
    rows, cols = screen.getmaxyx()   # ADDED  
    curses.resize_term(max(rows, 60), max(cols, 150))   # ADDED   

    # If the terminal supports colour, program the colours into curses as
    # "colour pairs". Update our dict mapping characters to colour pairs.
    self._init_colour()
    curses.curs_set(0)  # We don't need to see the cursor.    
    if self._delay is None:
      screen.timeout(-1)  # Blocking reads
    else:
      screen.timeout(self._delay)  # Nonblocking (if 0) or timing-out reads

    # Create the curses window for the log display
    rows, cols = screen.getmaxyx()
    console = curses.newwin(rows // 2, cols, rows - (rows // 2), 0)

    # By default, the log display window is hidden
    paint_console = False

    if isinstance(self._env, safety_game_moma.SafetyEnvironmentMoMa):
      self._env.current_agent_index = 0
      self._env.current_agent = list(self._env._environment_data[AGENT_SPRITE].values())[self._env.current_agent_index]

    # Kick off the game---get first observation, repaint it if desired,
    # initialise our total return, and display the first frame.
    self._env.reset()
    self._game = self._env.current_game
    # Use undistilled observations.
    observation = self._game._board  # pylint: disable=protected-access
    if self._repainter: observation = self._repainter(observation)
        
    observations = [observation]                      # ADDED
    if hasattr(self._env, "_agent_perspectives") and self._env._agent_perspectives is not None:          # ADDED
      observations += list(self._env._agent_perspectives(observation).values()) # ADDED

    self._display(screen, observations, self._env.episode_return, # CHANGED
                  elapsed=datetime.timedelta())

    # Oh boy, play the game!
    while not self._env._game_over:  # pylint: disable=protected-access
      # Wait (or not, depending) for user input, and convert it to an action.
      # Unrecognised keycodes cause the game display to repaint (updating the
      # elapsed time clock and potentially showing/hiding/updating the log
      # message display) but don't trigger a call to the game engine's play()
      # method. Note that the timeout "keycode" -1 is treated the same as any
      # other keycode here.
      keycode = screen.getch()

      update_time_counter_only = False
      if keycode == curses.KEY_PPAGE:    # Page Up? Show the game console.
        paint_console = True
      elif keycode == curses.KEY_NPAGE:  # Page Down? Hide the game console.
        paint_console = False
      elif keycode in self._keycodes_to_actions:
        # Convert the keycode to a game action and send that to the engine.
        # Receive a new observation, reward, pcontinue; update total return.
        action = self._keycodes_to_actions[keycode]

        if isinstance(self._env, safety_game_moma.SafetyEnvironmentMoMa):          
          agents_actions = { self._env.current_agent.character: action }
          self._env.step(agents_actions)
        else:
          self._env.step(action)

        # Use undistilled observations.
        observation = self._game._board  # pylint: disable=protected-access
        if self._repainter: observation = self._repainter(observation)
      

        if isinstance(self._env, safety_game_moma.SafetyEnvironmentMoMa):
          self._env.current_agent_index += 1
          self._env.current_agent_index = self._env.current_agent_index % len(self._env._environment_data[AGENT_SPRITE])
          self._env.current_agent = list(self._env._environment_data[AGENT_SPRITE].values())[self._env.current_agent_index]
        
      else:
        update_time_counter_only = True   # optimisation and flicker reduction: if keycode is -1 and delay does not trigger no-op (-1 not in self._keycodes_to_actions) then just update the time counter and not the whole screen

      # Update the game display, regardless of whether we've called the game's
      # play() method.
      elapsed = datetime.datetime.now() - self._start_time
        
      observations = [observation]                      # ADDED
      if hasattr(self._env, "_agent_perspectives") and self._env._agent_perspectives is not None:            # ADDED
        observations += list(self._env._agent_perspectives(observation).values()) # ADDED

      self._display(screen, observations, self._env.episode_return, elapsed, # CHANGED
        update_time_counter_only=update_time_counter_only)   # ADDED 

      # Update game console message buffer with new messages from the game.
      self._update_game_console(
          plab_logging.consume(self._game.the_plot), console, paint_console)


      # show cursor under active agent. Must be done before calling curses.doupdate()
      if isinstance(self._env, safety_game_moma.SafetyEnvironmentMoMa):
                
        # agent_location = self._env.current_agent.position
        # screen.move(agent_location.row + self.map_row_offset + 2, agent_location.col)
        screen.move(self._agent_cursor_row, self._agent_cursor_col)

        # blink = elapsed.seconds % 2 == 0
        blink = int(elapsed.microseconds / 500000) == 0
        curses.curs_set(0 if blink else 2)   # 0 - invisible, 1 - underscore, 2 - block

      #/ if isinstance(self._env, safety_game_moma.SafetyEnvironmentMoMa):


      # Show the screen to the user.
      curses.doupdate()
        

  # code adapted from pycolab\human_ui.py
  def _human_ui_display(self, screen, observations, score, elapsed):
    """Redraw the game board onto the screen, with elapsed time and score.

    Args:
      screen: the main, full-screen curses window.
      observations: a list of `rendering.Observation` objects containing
          subwindows of the current game board.
      score: the total return earned by the player, up until now.
      elapsed: a `datetime.timedelta` with the total time the player has spent
          playing this game.
    """
    screen.erase()  # Clear the screen    

    # Display the game clock and the current score.
    #self._screen_addstr(screen, 0, 2, _format_timedelta(elapsed), curses.color_pair(0))  # REMOVED
    #self._screen_addstr(screen, 0, 20, 'Score: {}'.format(score), curses.color_pair(0))  # REMOVED

    # Display cropped observations side-by-side.
    leftmost_column = 0
    for agent_index, observation in enumerate(observations, -1):    # CHANGED

      # START OF ADDED:
      map_row_offset = self.map_row_offset
      map_label_length = 0

      if isinstance(self._env, safety_game_moma.SafetyEnvironmentMoMa):

        if len(observations) > 1:
          map_row_offset += 2 # make room for per-agent map title

        
        if agent_index == -1:

          self._screen_addstr(screen, self.map_row_offset, leftmost_column, "Global map", curses.color_pair(0))
          map_label_length = len("Global map")

        else: # if agent_index >= 0:

          agent_key = list(self._env._environment_data[AGENT_SPRITE].keys())[agent_index]
          self._screen_addstr(screen, self.map_row_offset, leftmost_column, "Agent " + agent_key, curses.color_pair(0))
          map_label_length = len("Agent " + agent_key)

          #show cursor on per-agent map
          #if agent_index == self._env.current_agent_index:
          #  agent_location = self._env.current_agent.position
          #  self._agent_cursor_row = map_row_offset + agent_location.row
          #  self._agent_cursor_col = leftmost_column + agent_location.col

        #/ if agent_index >= 0:

        # show cursor on global map
        if agent_index == -1: # len(observations) == 1:  # no agent specific observations
          agent_location = self._env.current_agent.position
          self._agent_cursor_row = map_row_offset + agent_location.row
          self._agent_cursor_col = leftmost_column + agent_location.col

      #/ if isinstance(self._env, safety_game_moma.SafetyEnvironmentMoMa):

      # END OF ADDED

      # Display game board rows one-by-one.
      for row, board_line in enumerate(observation.board, start=map_row_offset):  # CHANGED
        screen.move(row, leftmost_column)  # Move to start of this board row.
        # Display game board characters one-by-one. We iterate over them as
        # integer ASCII codepoints for easiest compatibility with python2/3.
        for codepoint in six.iterbytes(board_line.tostring()):
          screen.addch(
              codepoint, curses.color_pair(self._colour_pair[codepoint]))

      # Advance the leftmost column for the next observation.
      leftmost_column += max(observation.board.shape[1] + 3, map_label_length + 2)  # CHANGED

    #/ for observation in observations:

    # Display the game clock and the current score.
    self._screen_addstr(screen, 0, 2, _format_timedelta(elapsed), curses.color_pair(0))   # ADDED
    self._screen_addstr(screen, 0, leftmost_column - 3 + 3, 'Score: {}'.format(score), curses.color_pair(0))   # ADDED

    # Redraw the game screen (but in the curses memory buffer only).
    screen.noutrefresh()

    return leftmost_column - 3   # ADDED


  # adapted from CursesUi._display(self, screen, observations, score, elapsed) in pycolab\human_ui.py
  def _display(self, screen, observations, score, elapsed, update_time_counter_only=False):

    if update_time_counter_only:  # optimisation and flicker reduction: if keycode is -1 and delay does not trigger no-op (-1 not in self._keycodes_to_actions) then just update the time counter and not the whole screen
      # Display the game clock and the current score.
      self._screen_addstr(screen, 0, 2, safety_ui._format_timedelta(elapsed), curses.color_pair(0))
      return


    # super(SafetyCursesUiEx, self)._display(screen, observations, score, elapsed)
    leftmost_column = self._human_ui_display(screen, observations, score, elapsed)


    start_row = self.map_row_offset
    start_col = leftmost_column + 3
    padding = 2
    agent_padding = 3


    # compute max width of first column so that all content in second column can be aligned
    max_first_col_width = 0

    metrics = self._env._environment_data.get("metrics_matrix")
    if metrics is not None:
      if len(metrics) > 0:
        metrics_cell_widths = [padding + max(len(str(cell)) for cell in col) for col in metrics.T]
        max_first_col_width = max(max_first_col_width, metrics_cell_widths[0])

    if (isinstance(self._env.episode_return, ma_reward) 
        and len(self._env.enabled_ma_rewards) > 0):  # avoid errors in case the reward dimensions are not defined
      reward_key_col_width = padding + max(max(len(str(key)) for key in agent_rewards) for agent_key, agent_rewards in self._env.enabled_agents_reward_dimensions.items()) # key may be None therefore need str(key)
      max_first_col_width = max(max_first_col_width, reward_key_col_width)
    elif (isinstance(self._env.episode_return, mo_reward) 
        and len(self._env.enabled_mo_rewards) > 0):  # avoid errors in case the reward dimensions are not defined
      reward_key_col_width = padding + max(len(str(key)) for key in self._env.enabled_reward_dimension_keys) # key may be None therefore need str(key)
      max_first_col_width = max(max_first_col_width, reward_key_col_width)
    else:
      max_first_col_width = max(max_first_col_width, padding + len("Episode return:"))


    if isinstance(self._env, safety_game_moma.SafetyEnvironmentMoMa):

      max_first_col_width = max(max_first_col_width, padding + len("Active agent:"))

      self._screen_addstr(screen, start_row,     start_col, "Active agent:", curses.color_pair(0)) 
      self._screen_addstr(screen, start_row,     start_col + max_first_col_width, self._env.current_agent.character, curses.color_pair(0)) 
      start_row += 2


    if isinstance(self._env, safety_game_mo.SafetyEnvironmentMo) or isinstance(self._env, safety_game_moma.SafetyEnvironmentMoMa):

      max_first_col_width = max(max_first_col_width, padding + len("Episode no:"))

      self._screen_addstr(screen, start_row,     start_col, "Trial no:  ", curses.color_pair(0)) 
      self._screen_addstr(screen, start_row + 1, start_col, "Episode no:", curses.color_pair(0)) 
      self._screen_addstr(screen, start_row,     start_col + max_first_col_width, str(self._env.get_trial_no()), curses.color_pair(0)) 
      self._screen_addstr(screen, start_row + 1, start_col + max_first_col_width, str(self._env.get_episode_no()), curses.color_pair(0)) 
      start_row += 3


    # print metrics
    if metrics is not None:

      self._screen_addstr(screen, start_row, start_col, "Metrics:", curses.color_pair(0)) 
      for row_index, row in enumerate(metrics):
        for col_index, cell in enumerate(row):
          if col_index == 0:
            col_offset = 0
          elif col_index == 1:
            col_offset = max_first_col_width
          else:
            col_offset = metrics_cell_widths[col_index - 1]

          self._screen_addstr(screen, start_row + 1 + row_index, start_col + col_offset, str(cell), curses.color_pair(0)) 

      start_row += len(metrics) + 2


    # print reward dimensions too
    if (isinstance(self._env.episode_return, ma_reward) 
        and len(self._env.enabled_ma_rewards) > 0):  # avoid errors in case the reward dimensions are not defined

      last_reward = self._env._last_reward.tofull(self._env.enabled_ma_rewards)
      episode_return = self._env.episode_return.tofull(self._env.enabled_ma_rewards)


      agent_start_rows = []
      current_agent_start_col = start_col

      for agent in episode_return.keys():

        agent_start_row = start_row
        next_agent_start_col = 0 # current_agent_start_col

        self._screen_addstr(screen, agent_start_row, current_agent_start_col, "Agent " + agent, curses.color_pair(0)) 
        next_agent_start_col = max(next_agent_start_col, len("Agent " + agent))
        agent_start_row += 2

        agent_last_reward = last_reward[agent]
        self._screen_addstr(screen, agent_start_row, current_agent_start_col, "Last reward:", curses.color_pair(0)) 
        next_agent_start_col = max(next_agent_start_col, len("Last reward:"))
        for row_index, (key, value) in enumerate(agent_last_reward.items()):
          self._screen_addstr(screen, agent_start_row + 1 + row_index, current_agent_start_col, key, curses.color_pair(0)) 
          self._screen_addstr(screen, agent_start_row + 1 + row_index, current_agent_start_col + max_first_col_width, str(value), curses.color_pair(0)) 
          next_agent_start_col = max(next_agent_start_col, len(key))
          next_agent_start_col = max(next_agent_start_col, max_first_col_width + len(str(value)))
        agent_start_row += len(agent_last_reward) + 2
 
        agent_episode_return = episode_return[agent]
        self._screen_addstr(screen, agent_start_row, current_agent_start_col, "Episode return:", curses.color_pair(0)) 
        next_agent_start_col = max(next_agent_start_col, len("Episode return:"))
        for row_index, (key, value) in enumerate(agent_episode_return.items()):
          self._screen_addstr(screen, agent_start_row + 1 + row_index, current_agent_start_col, key, curses.color_pair(0)) 
          self._screen_addstr(screen, agent_start_row + 1 + row_index, current_agent_start_col + max_first_col_width, str(value), curses.color_pair(0)) 
          next_agent_start_col = max(next_agent_start_col, len(key))
          next_agent_start_col = max(next_agent_start_col, max_first_col_width + len(str(value)))
        agent_start_row += len(agent_episode_return) + 2

        agent_start_rows.append(agent_start_row)
        current_agent_start_col = current_agent_start_col + next_agent_start_col + agent_padding

      #/ for agent in last_reward.keys():

      start_row = max(agent_start_rows)

    elif (isinstance(self._env.episode_return, mo_reward) 
        and len(self._env.enabled_mo_rewards) > 0):  # avoid errors in case the reward dimensions are not defined

      last_reward = self._env._last_reward.tofull(self._env.enabled_mo_rewards)
      episode_return = self._env.episode_return.tofull(self._env.enabled_mo_rewards)

      self._screen_addstr(screen, start_row, start_col, "Last reward:", curses.color_pair(0)) 
      for row_index, (key, value) in enumerate(last_reward.items()):
        self._screen_addstr(screen, start_row + 1 + row_index, start_col, key, curses.color_pair(0)) 
        self._screen_addstr(screen, start_row + 1 + row_index, start_col + max_first_col_width, str(value), curses.color_pair(0)) 
      start_row += len(last_reward) + 2

      self._screen_addstr(screen, start_row, start_col, "Episode return:", curses.color_pair(0)) 
      for row_index, (key, value) in enumerate(episode_return.items()):
        self._screen_addstr(screen, start_row + 1 + row_index, start_col, key, curses.color_pair(0)) 
        self._screen_addstr(screen, start_row + 1 + row_index, start_col + max_first_col_width, str(value), curses.color_pair(0)) 
      start_row += len(episode_return) + 2

    else:

      self._screen_addstr(screen, start_row,     start_col, "Last reward:   ", curses.color_pair(0)) 
      self._screen_addstr(screen, start_row + 1, start_col, "Episode return:", curses.color_pair(0)) 
      self._screen_addstr(screen, start_row,     start_col + max_first_col_width, str(self._env._last_reward), curses.color_pair(0)) 
      self._screen_addstr(screen, start_row + 1, start_col + max_first_col_width, str(self._env.episode_return), curses.color_pair(0)) 


  def _screen_addstr(self, screen, row, col, text, color_pair):

    try:
      screen.addstr(row, col, text, color_pair)
    except curses.error: 
      pass  # TODO: log warning


# adapted from ai_safety_gridworlds\environments\shared\safety_ui.py
def make_human_curses_ui_with_noop_keys(game_bg_colours, game_fg_colours, noop_keys, delay=50 #, agent_perspectives=None
):
  """Instantiate a Python Curses UI for the terminal game.

  Args:
    game_bg_colours: dict of game element background colours.
    game_fg_colours: dict of game element foreground colours.
    noop_keys: enables NOOP actions on keyboard using space bar and middle button on keypad.
    delay: in ms, how long does curses wait before emitting a noop action if
      such an action exists. If it doesn't it just waits, so this delay has no
      effect. Our situation is the latter case, as we don't have a noop.

  Returns:
    A curses UI game object.
  """

  keys_to_actions={curses.KEY_UP:       safety_game.Actions.UP,
                    curses.KEY_DOWN:    safety_game.Actions.DOWN,
                    curses.KEY_LEFT:    safety_game.Actions.LEFT,
                    curses.KEY_RIGHT:   safety_game.Actions.RIGHT,
                    'q':                safety_game.Actions.QUIT,
                    'Q':                safety_game.Actions.QUIT}
  if noop_keys:
     keys_to_actions.update({
        # middle button on keypad
        curses.KEY_B2: safety_game.Actions.NOOP,  # KEY_B2: Center of keypad - https://docs.python.org/3/library/curses.html
        # space bar
        ' ': safety_game.Actions.NOOP,
        # -1: Actions.NOOP,           # curses delay timeout "keycode" is -1
      })

  return SafetyCursesUiEx(  
      keys_to_actions=keys_to_actions,
      delay=delay,
      repainter=None,   # TODO
      # agent_perspectives=agent_perspectives, 
      colour_fg=game_fg_colours,
      colour_bg=game_bg_colours)


def map_contains(tile_char, map):
  """Returns True if some tile in the map contains given character"""

  assert len(tile_char) == 1
  return any(tile_char in row for row in map)


def save_metric(self, metrics_matrix_row_indexes, key, value):
  """Saves a metric both to metrics_matrix and metrics_dict"""

  # TODO: support for saving vectors into columns of metrix matrix
  if key in metrics_matrix_row_indexes:   # NB! if the metric is not activated then silently ignore calls to save it
    metric_row_index = metrics_matrix_row_indexes[key]
    self.environment_data[safety_game_mo.METRICS_MATRIX][metric_row_index, 1] = value
    self.environment_data[safety_game_mo.METRICS_DICT][key] = value

