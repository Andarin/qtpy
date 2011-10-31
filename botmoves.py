#!/usr/bin/env python
#
# QTPy Bot move database
#
# John Driscoll

import cgi
from google.appengine.ext import db

class BotMoves(db.Model):
  """ Interface for database of bot moves """
  
  state = db.StringProperty()                         # State of the game before the bot's move is made in standard notation
  move = db.StringProperty()                          # Bot's move in standard notation
  played = db.IntegerProperty(default=1)              # Number of games the move has been played in
  wins = db.IntegerProperty(default=0)                # Number of games won using this move
  losses = db.IntegerProperty(default=0)              # Number of games lost using this move
  draws = db.IntegerProperty(default=0)               # Number of games drawn using this move
  played_in_sequence = db.IntegerProperty(default=1)  # Number of times in-a-row this move has been played
  winp = db.FloatProperty(default=0.0)                # Probability of win
  lossp = db.FloatProperty(default=0.0)               # Probabilty of loss
  drawp = db.FloatProperty(default=0.0)               # Probability of draw
  
  # Square number translation tables
  _rot90 =  [ 7, 4, 1, 8, 5, 2, 9, 6, 3 ]
  _rot180 = [ 9, 8, 7, 6, 5, 4, 3, 2, 1 ]
  _rot270 = [ 3, 6, 9, 2, 5, 8, 1, 4, 7 ]
  _fliph =  [ 3, 2, 1, 6, 5, 4, 9, 8, 7 ]
  _flipv =  [ 7, 8, 9, 4, 5, 6, 1, 2, 3 ]
  _table =  { '0':    [ _rot90 ],         '-0':   [ _rot270 ],
              '1':    [ _rot180 ],        '-1':   [ _rot180 ],
              '2':    [ _rot270 ],        '-2':   [ _rot90 ],
              'v':    [ _flipv ],         '-v':   [ _flipv ],
              'h':    [ _fliph ],         '-h':   [ _fliph ],
              '0h':   [ _rot90, _fliph ], '-0h':  [ _fliph, _rot270 ],
              '0v':   [ _rot90, _flipv ], '-0v':  [ _flipv, _rot270 ] }
  _valid_keys = [ None, '0', '1', '2', 'v', 'h', '0v', '0h' ]
  
  @staticmethod
  def update_state(state, move, outcome):
    """ Update (or create) outcome probabilities for a game state and move combo
    Arguments:
      state and move: standard notation game strings
      outcome: array of player scores [ player, bot ]
    """
    
    from bot import Bot
    game = BotMoves.find_state(state, move)
    outcome = BotMoves.outcome(outcome)
    if game:
      if game[0].count(2) > 1: # Dup!
        # Use the most played move
        dups = []
        for game in game[0]: dups.append(game)
        dups.sort(key=lambda g: g.played, reverse=True)
        for i in range(1,len(dups)): dups[i].delete()
        game = dups[0]
      else:
        game = game[0].fetch(1)[0]
      game.played += 1
      if outcome == 1: game.wins += 1
      elif outcome == 0: game.draws += 1
      else: game.losses += 1
      game.winp = float(game.wins) / float(game.played);
      game.lossp = float(game.losses) / float(game.played);
      game.drawp = float(game.draws) / float(game.played);
      if game.played_in_sequence >= Bot.noise_factor():
        game.played_in_sequence = 0
      else:
        game.played_in_sequence += 1
      game.put()
    else:
      # Create new record
      w = d = l = 0
      if outcome == 1: w = 1
      elif outcome == 0: d = 1
      else: l = 1
      game = BotMoves(state=state,move=move,wins=w,draws=d,losses=l,winp=float(w),drawp=float(d),lossp=float(l))
      game.put()
    # Add mapped flag if all valid moves have been played
    from botmovesmapped import BotMovesMapped
    if not BotMovesMapped.has(game.state):
      from state import State
      state = State(game.state)
      if not Bot.get_missing_move(state):
        BotMovesMapped(state=game.state).put()
  
  @staticmethod
  def translate(moves, key):
    """ Translates a plyable move list based on the key """
  
    if not key: return moves
    tables = BotMoves._table[key]
    out = []
    for move in moves: out.append(move)
    for table in tables:
      for i in range(len(out)):
        sq1 = table[out[i][0]-1] if out[i][0] > 0 else 0
        sq2 = table[out[i][1]-1] if out[i][1] > 0 else 0
        if sq1 > sq2: sq1,sq2 = sq2, sq1
        out[i] = (sq1,sq2)
    return out
  
  @staticmethod
  def find_states(state):
    """ Finds all game states of any orientation that equal state. """
    
    states = [state]
    my = BotMoves
    def t(state, k): return my.translate(state, k)
    a = BotMoves.plyable(state)
    t = BotMoves.translate
    s = BotMoves.searchable
    # Look for game rotated 90 degrees
    a90 = t(a, '0')
    states.append(s(a90))
    # Look for game rotated 180 degrees
    a180 = t(a90, '0')
    states.append(s(a180))
    # Look for game rotated 270 degrees
    states.append(s(t(a180, '0')))
    # Look for game flipped vertically
    states.append(s(t(a, 'v')))
    # Look for game flipped horizontally
    states.append(s(t(a, 'h')))
    # Look for game flipped vertically and rotated 90 degrees
    states.append(s(t(a90, 'v')))
    # Look for game flipped horizontally and rotated 90 degrees
    states.append(s(t(a90, 'h')))
    return my.all().filter('state IN', states)
  
  @staticmethod
  def find_state(state, move=None, outcome=None, key=None, my=None):
    """ Finds a game state in the DB or returns None.
    state is a game state in standard notation.
    Looks for games of the supplied state in different variations
    and optionally with the same move and outcome.
    
    Arguments:
      state: game string in standard notation
      move: one or two game moves in standard notation (two moves in the case that the
            the first move is a collapse)
      outcome: an integer where -1 = bot loss, 0 = draw, 1 = bot win
    
    Returns an array
    [ 0: the game records in the DB,
      1: the key used to transform the supplied state into the variation found in the DB ]
    
    If key is None, then the game was stored in the database in the same format supplied
    Key is a string consisting of any of these (although some combinations are not
    supported because they are redundant)
      0: The state was rotated 90 degrees
      1: The state was rotated 180 degrees
      2: The state was rotated 270 degrees
      v: The state was flipped vertically
      h: The state was flipped horizontally
    Supported keys: 0, 1, 2, h, v, 0h, 0v
    """
    
    if not my: my = BotMoves
    def get(state, move=None, outcome=None):
      # Get helper: return query object for oriented state string
      q = my.all().filter('state =', BotMoves.searchable(state))
      if move: q.filter('move =', BotMoves.searchable(move))
      if outcome:
        if outcome == 1: q.filter('wins =', 1)
        elif outcome == 0: q.filter('draws =', 1)
        else: q.filter('losses =', 1)
      return q
    def t(state, k): return my.translate(state, k)
    a = BotMoves.plyable(state)
    m = BotMoves.plyable(move) if move else None
    # key provided?
    if key: return get(t(a,key),t(m,key),outcome)
    t = BotMoves.translate
    # Look for game
    k = None
    games = get(a, m, outcome)
    if not games.count(1):
      # Look for game rotated 90 degrees
      k = '0'
      a90 = t(a, k); m90 = t(m, k) if m else None
      games = get(a90, m90, outcome)
      if not games.count(1):
        # Look for game rotated 180 degrees
        k = '1'
        a180 = t(a90, '0'); m180 = t(m90, '0') if m else None
        games = get(a180, m180, outcome)
        if not games.count(1):
          # Look for game rotated 270 degrees
          k = '2'
          games = get(t(a180, '0'), t(m180, '0') if m else None, outcome)
          if not games.count(1):
            # Look for game flipped vertically
            k = 'v'
            games = get(t(a, k), t(m, k) if m else None, outcome)
            if not games.count(1):
              # Look for game flipped horizontally
              k = 'h'
              games = get(t(a, k), t(m, k) if m else None, outcome)
              if not games.count(1):
                # Look for game flipped vertically and rotated 90 degrees
                k = '0v'
                games = get(t(a90, 'v'), t(m90, 'v') if m else None, outcome)
                if not games.count(1):
                  # Look for game flipped horizontally and rotated 90 degrees
                  k = '0h'
                  games = get(t(a90, 'h'), t(m90, 'h') if m else None, outcome)
                  if not games.count(1): return None
    return [ games, k ]
  
  @staticmethod
  def transform(state, key):
    """ Perform quick re-orientation on a movelist """
    
    if key == None: return state
    return BotMoves.searchable(BotMoves.translate(BotMoves.plyable(state), key))
  
  @staticmethod
  def fix(state, key):
    """ Perform quick un-re-orientation on a movelist """
    
    if key == None: return state
    return BotMoves.searchable(BotMoves.translate(BotMoves.plyable(state), '-%s'%key if key[0] != '-' else key[1:]))
  
  @staticmethod
  def plyable(state):
    """ Returns an array of tuples of the supplied game string [ (sq1, sq2), ... ]
    
    Opposite of searchable(moves)
    
    state is a game state string in standard notation
    """
    
    out = []
    for move in state.split('/'): out.append((int(move[0]),int(move[1])));
    return out
  
  @staticmethod
  def searchable(moves):
    """ Returns a standard notation string based on the supplied array of move tuples
    
    Opposite of plyable
    """
    
    out = []
    for move in moves: out.append('%d%d'%(move[0],move[1]))
    return '/'.join(out)
  
  @staticmethod
  def outcome(scores):
    """ Returns integer describing the game outcome: -1 for player win, 0 for draw, 1 for bot win """
    
    if scores[0] == scores[1]: return 0
    elif scores[0] > scores[1]: return -1
    return 1




























