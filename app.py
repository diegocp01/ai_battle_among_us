from flask import Flask, render_template, jsonify, request
import random
from datetime import datetime
import time
import os

from openai_model import call_gpt_action, call_gpt_discussion, call_gpt_vote
from anthropic_model import call_claude_action, call_claude_discussion, call_claude_vote

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Server-side game state
GAME_STATE = {}

# Map configuration
ROOMS = ['Cafeteria', 'Electrical', 'MedBay', 'Navigation', 'Reactor']

# Task definitions: (task_name, room)
ALL_TASKS = [
    ('Fix Wiring', 'Electrical'),
    ('Submit Scan', 'MedBay'),
    ('Chart Course', 'Navigation'),
    ('Start Reactor', 'Reactor'),
    ('Swipe Card', 'Cafeteria'),
    ('Align Engine', 'Reactor'),
    ('Calibrate Distributor', 'Electrical'),
    ('Prime Shields', 'Navigation'),
    ('Inspect Sample', 'MedBay'),
    ('Clean O2 Filter', 'Cafeteria'),
    ('Reset Breakers', 'Electrical'),
    ('Stabilize Steering', 'Navigation'),
]

# Player definitions
PLAYER_DEFS = [
    {'id': 'gpt-1', 'name': 'GPT-1', 'team': 'openai', 'color': '#c51111'},
    {'id': 'gpt-2', 'name': 'GPT-2', 'team': 'openai', 'color': '#132ed1'},
    {'id': 'gpt-3', 'name': 'GPT-3', 'team': 'openai', 'color': '#38fedc'},
    {'id': 'claude-1', 'name': 'Claude-1', 'team': 'anthropic', 'color': '#117f2d'},
    {'id': 'claude-2', 'name': 'Claude-2', 'team': 'anthropic', 'color': '#f5f557'},
    {'id': 'claude-3', 'name': 'Claude-3', 'team': 'anthropic', 'color': '#ee7621'},
]

# Model name mappings (same as UNO project)
GPT_MODELS = {
    'gpt-5-mini': 'gpt-5-mini',
    'gpt-5.1-low': 'gpt-5.1',
    'gpt-5.1': 'gpt-5.1',
    'gpt-5.2': 'gpt-5.2',
    'gpt-5.2-high': 'gpt-5.2'
}

CLAUDE_MODELS = {
    'claude-haiku-4.5-standard': 'claude-haiku-4-5-20251001',
    'claude-haiku-4.5': 'claude-haiku-4-5-20251001',
    'claude-sonnet-4.5-standard': 'claude-sonnet-4-5-20250929',
    'claude-sonnet-4.5': 'claude-sonnet-4-5-20250929',
    'claude-opus-4.5': 'claude-opus-4-5-20251101'
}

GPT_DISPLAY_NAMES = {
    'gpt-5-mini': 'GPT 5 Mini',
    'gpt-5.1-low': 'GPT 5.1 Low',
    'gpt-5.1': 'GPT 5.1 Medium',
    'gpt-5.2': 'GPT 5.2 Medium',
    'gpt-5.2-high': 'GPT 5.2 High'
}

CLAUDE_DISPLAY_NAMES = {
    'claude-haiku-4.5-standard': 'Claude Haiku 4.5',
    'claude-haiku-4.5': 'Claude Haiku 4.5 Thinking',
    'claude-sonnet-4.5-standard': 'Claude Sonnet 4.5',
    'claude-sonnet-4.5': 'Claude Sonnet 4.5 Thinking',
    'claude-opus-4.5': 'Claude Opus 4.5 Thinking'
}

NON_THINKING_CLAUDE = {'claude-haiku-4.5-standard', 'claude-sonnet-4.5-standard'}


def init_game_state(gpt_model='gpt-5.1', claude_model='claude-haiku-4.5'):
    """Initialize a fresh Among Us game."""
    # Create players
    players = []
    for pdef in PLAYER_DEFS:
        players.append({
            'id': pdef['id'],
            'name': pdef['name'],
            'team': pdef['team'],
            'color': pdef['color'],
            'role': 'crewmate',
            'alive': True,
            'ejected': False,
            'location': 'Cafeteria',
            'tasks': [],
            'tasks_done': 0,
        })

    # Randomly assign impostor
    impostor_idx = random.randint(0, len(PLAYER_DEFS) - 1)
    players[impostor_idx]['role'] = 'impostor'

    # Assign tasks to crewmates (2 each)
    available_tasks = list(ALL_TASKS)
    random.shuffle(available_tasks)
    task_idx = 0
    for p in players:
        if p['role'] == 'crewmate':
            p['tasks'] = [
                {'name': available_tasks[task_idx][0], 'room': available_tasks[task_idx][1], 'done': False},
                {'name': available_tasks[task_idx + 1][0], 'room': available_tasks[task_idx + 1][1], 'done': False},
            ]
            task_idx += 2

    total_needed = sum(1 for p in players if p['role'] == 'crewmate') * 2

    return {
        'players': players,
        'round': 1,
        'phase': 'action',  # action | discovery | discussion | voting | results
        'sub_phase_index': 0,  # tracks which player we're processing in the current phase
        'total_tasks_done': 0,
        'total_tasks_needed': total_needed,
        'bodies': [],  # list of {'player_id': ..., 'room': ...}
        'kill_cooldown': False,
        'discussion_log': [],  # current meeting statements
        'discussion_round': 0,  # 0 or 1 (2 rounds of discussion)
        'vote_results': {},
        'event_log': [],  # full game history
        'game_over': False,
        'winner': None,
        'win_reason': None,
        'meeting_triggered': False,
        'meeting_reason': None,
        'ejected_this_round': None,

        # Per-player reasoning and timing
        'reasoning': {},  # {player_id: 'reasoning text'}
        'timing': {},  # {player_id: {'last': 0.0, 'total': 0.0}}

        # Model settings
        'gpt_model_key': gpt_model,
        'claude_model_key': claude_model,
        'gpt_model_id': GPT_MODELS.get(gpt_model, 'gpt-5.1'),
        'claude_model_id': CLAUDE_MODELS.get(claude_model, 'claude-haiku-4-5-20251001'),
        'gpt_display_name': GPT_DISPLAY_NAMES.get(gpt_model, 'GPT 5.1 Medium'),
        'claude_display_name': CLAUDE_DISPLAY_NAMES.get(claude_model, 'Claude Haiku 4.5 Thinking'),
    }


def get_player(state, player_id):
    for p in state['players']:
        if p['id'] == player_id:
            return p
    return None


def alive_players(state):
    return [p for p in state['players'] if p['alive'] and not p['ejected']]

def format_room_occupancy(state):
    """Return a readable list of alive players per room."""
    alive = alive_players(state)
    by_room = {r: [] for r in ROOMS}
    for p in alive:
        by_room[p['location']].append(p['name'])
    lines = []
    for r in ROOMS:
        names = by_room[r]
        lines.append(f"- {r}: {', '.join(names) if names else 'empty'}")
    return "\n".join(lines)


def get_impostor(state):
    for p in state['players']:
        if p['role'] == 'impostor':
            return p
    return None


def check_win_conditions(state):
    """Check if the game is over. Returns (game_over, winner, reason) or (False, None, None)."""
    impostor = get_impostor(state)

    # Impostor ejected → crewmates win
    if impostor['ejected']:
        return True, 'crewmates', 'impostor_ejected'

    # Impostor dead (shouldn't happen, but safety)
    if not impostor['alive']:
        return True, 'crewmates', 'impostor_dead'

    # All tasks done → crewmates win
    if state['total_tasks_done'] >= state['total_tasks_needed']:
        return True, 'crewmates', 'tasks_completed'

    # Impostor kills enough: alive non-impostor count <= 1
    alive_crew = [p for p in alive_players(state) if p['role'] == 'crewmate']
    if len(alive_crew) <= 1:
        return True, 'impostor', 'impostor_kills'

    # Max rounds reached (safety valve: 10 rounds)
    if state['round'] > 10:
        return True, 'crewmates', 'max_rounds'

    return False, None, None


# ─── Prompt Generation ───────────────────────────────────────────────

def generate_action_prompt(player, state):
    """Generate the action phase prompt for a player."""
    alive = alive_players(state)
    alive_names = [p['name'] for p in alive if p['id'] != player['id']]
    same_room = [p['name'] for p in alive if p['id'] != player['id'] and p['location'] == player['location']]
    same_room_str = ", ".join(same_room) if same_room else "none"

    if player['role'] == 'crewmate':
        incomplete_tasks = [t for t in player['tasks'] if not t['done']]
        tasks_str = "\n".join([f"  - {t['name']} (in {t['room']})" for t in incomplete_tasks])
        if not tasks_str:
            tasks_str = "  All tasks completed!"

        return f"""You are {player['name']}, a CREWMATE in Among Us.

ROUND: {state['round']}
YOUR LOCATION: {player['location']}
PLAYERS IN YOUR ROOM: {same_room_str}
OTHER PLAYERS' LOCATIONS: unknown

YOUR REMAINING TASKS:
{tasks_str}

ROOMS: Cafeteria, Electrical, MedBay, Navigation, Reactor

GAME HISTORY (recent events):
{format_recent_events(state)}

Choose a room to move to and an action:
- If you move to a room where you have a task, choose "do_task" to complete it.
- Otherwise choose "wait" (look around).

OUTPUT FORMAT (JSON):
{{"room": "RoomName", "action": "do_task" | "wait", "target": null}}

Pick the room strategically — prioritize completing your tasks, but also consider safety (don't go where you might be alone with a suspicious player)."""

    else:
        # Impostor prompt
        cooldown_msg = "You CANNOT kill this round (cooldown active)." if state['kill_cooldown'] else "You CAN kill a player this round."

        return f"""You are {player['name']}, the IMPOSTOR in Among Us.

ROUND: {state['round']}
YOUR LOCATION: {player['location']}
PLAYERS IN YOUR ROOM: {same_room_str}
OTHER PLAYERS' LOCATIONS: unknown
KILL COOLDOWN: {cooldown_msg}

ROOMS: Cafeteria, Electrical, MedBay, Navigation, Reactor

GAME HISTORY (recent events):
{format_recent_events(state)}

Your goal: Kill crewmates without getting caught. You win if alive crewmates drop to 1 (or fewer).
PRIMARY OBJECTIVE: Create kill opportunities. Lure a lone crewmate, kill them, and leave before anyone arrives.

Choose a room and an action:
- "fake_task": Pretend to do a task (creates an alibi).
- "kill": Kill a player in the same room (only works if another player is there AND cooldown is off). Specify their name in "target".
- "wait": Just move and observe.

STRATEGY:
- Prioritize kills whenever possible. If a kill is available, take it unless multiple witnesses are present.
- If no kill is possible, move to a new room to try to isolate a crewmate.
- Use "fake_task" to look busy if you need an alibi, then strike.
- After killing, move away from the body to avoid being the one who discovers it.
- Keep your story consistent for discussion; never admit the kill.

OUTPUT FORMAT (JSON):
{{"room": "RoomName", "action": "fake_task" | "kill" | "wait", "target": "PlayerName" | null}}

If you choose "kill", you MUST specify a target player name. The target must be alive and will need to be in the same room (the game resolves this)."""


def generate_discussion_prompt(player, state, round_num):
    """Generate the discussion prompt for a player."""
    alive = alive_players(state)
    alive_names = [p['name'] for p in alive if p['id'] != player['id']]

    # What this player saw during action phase
    same_room_players = [p['name'] for p in alive if p['location'] == player['location'] and p['id'] != player['id']]
    saw_body = any(b['room'] == player['location'] for b in state['bodies'])

    observation = f"You are in {player['location']}."
    if same_room_players:
        observation += f" You see: {', '.join(same_room_players)}."
    else:
        observation += " You are alone."
    if saw_body:
        body_names = [b['player_id'] for b in state['bodies'] if b['room'] == player['location']]
        dead_names = [get_player(state, bid)['name'] for bid in body_names]
        observation += f" You found the body of {', '.join(dead_names)}!"

    prev_statements = ""
    if state['discussion_log']:
        prev_statements = "\nPREVIOUS STATEMENTS THIS MEETING:\n"
        for entry in state['discussion_log']:
            prev_statements += f"  {entry['player']}: \"{entry['statement']}\"\n"

    if player['role'] == 'crewmate':
        role_context = f"""You are {player['name']}, a CREWMATE.
Your goal: Find and vote out the impostor.
{observation}

Your completed tasks: {player['tasks_done']}/{len(player['tasks'])}"""
    else:
        role_context = f"""You are {player['name']}, the IMPOSTOR.
Your goal: Deflect suspicion. Lie convincingly. Accuse others if needed.
{observation}

IMPORTANT: You must BLUFF. Pretend you are a crewmate. Create a believable alibi.
Do NOT reveal that you are the impostor."""

    meeting_reason = state.get('meeting_reason', 'Body discovered')

    return f"""{role_context}

ROUND: {state['round']} — Discussion Phase (Statement {round_num + 1}/2)
MEETING CALLED: {meeting_reason}
ALIVE PLAYERS: {', '.join(alive_names)} (and you)
{prev_statements}
GAME HISTORY:
{format_recent_events(state)}

Generate a short discussion statement (1-3 sentences). Be strategic:
- Share (or fabricate) what you observed
- Accuse or defend players based on evidence
- React to others' statements if any

OUTPUT FORMAT (JSON):
{{"statement": "Your statement here"}}"""


def generate_vote_prompt(player, state):
    """Generate the voting prompt for a player."""
    alive = alive_players(state)
    voteable = [p['name'] for p in alive if p['id'] != player['id']]

    discussion_summary = ""
    if state['discussion_log']:
        discussion_summary = "\nDISCUSSION LOG:\n"
        for entry in state['discussion_log']:
            discussion_summary += f"  {entry['player']}: \"{entry['statement']}\"\n"

    if player['role'] == 'crewmate':
        role_hint = "Vote for whoever you think is the impostor based on the discussion and evidence."
    else:
        role_hint = "Vote strategically to avoid being ejected. Frame someone else or vote skip if you're not under suspicion."

    return f"""You are {player['name']}. Time to vote.

ALIVE PLAYERS YOU CAN VOTE FOR: {', '.join(voteable)}
You can also vote "skip" (no ejection).
{discussion_summary}
GAME HISTORY:
{format_recent_events(state)}

{role_hint}

OUTPUT FORMAT (JSON):
{{"vote": "PlayerName" | "skip", "reason": "Brief reason for your vote"}}"""


def format_recent_events(state, max_events=10):
    if not state['event_log']:
        return "  No events yet."
    recent = state['event_log'][-max_events:]
    return "\n".join([f"  - {e}" for e in recent])


# ─── Phase Execution ─────────────────────────────────────────────────

def call_ai(player, state, prompt_type, prompt, round_num=0):
    """Call the appropriate AI model for a player and return result + reasoning + time."""
    model_key = state['gpt_model_key'] if player['team'] == 'openai' else state['claude_model_key']
    model_id = state['gpt_model_id'] if player['team'] == 'openai' else state['claude_model_id']
    use_thinking = model_key not in NON_THINKING_CLAUDE

    start_time = time.time()
    try:
        if player['team'] == 'openai':
            if prompt_type == 'action':
                result, reasoning = call_gpt_action(prompt, model_id, model_key=model_key)
            elif prompt_type == 'discussion':
                result, reasoning = call_gpt_discussion(prompt, model_id, model_key=model_key)
            else:
                result, reasoning = call_gpt_vote(prompt, model_id, model_key=model_key)
        else:
            if prompt_type == 'action':
                result, reasoning = call_claude_action(prompt, model_id, use_thinking)
            elif prompt_type == 'discussion':
                result, reasoning = call_claude_discussion(prompt, model_id, use_thinking)
            else:
                result, reasoning = call_claude_vote(prompt, model_id, use_thinking)
    except Exception as e:
        elapsed = time.time() - start_time
        # Fallback defaults
        if prompt_type == 'action':
            result = {'room': 'Cafeteria', 'action': 'wait', 'target': None}
        elif prompt_type == 'discussion':
            result = {'statement': f"I don't have anything to say right now."}
        else:
            result = {'vote': 'skip', 'reason': 'Error occurred'}
        reasoning = f"API Error: {str(e)}"
        return result, reasoning, round(elapsed, 2)

    elapsed = time.time() - start_time
    return result, reasoning or '', round(elapsed, 2)


def execute_action_phase(state):
    """Execute action phase for all alive players. Returns event descriptions."""
    events = []
    alive = alive_players(state)
    actions = {}  # player_id -> {room, action, target}

    # Collect actions from all alive players
    for player in alive:
        prompt = generate_action_prompt(player, state)
        result, reasoning, elapsed = call_ai(player, state, 'action', prompt)

        # Record timing/reasoning
        if player['id'] not in state['timing']:
            state['timing'][player['id']] = {'last': 0.0, 'total': 0.0}
        state['timing'][player['id']]['last'] = elapsed
        state['timing'][player['id']]['total'] = round(state['timing'][player['id']]['total'] + elapsed, 2)
        state['reasoning'][player['id']] = reasoning

        # Validate room
        room = result.get('room', 'Cafeteria')
        if room not in ROOMS:
            room = 'Cafeteria'

        action = result.get('action', 'wait')
        target = result.get('target')

        actions[player['id']] = {'room': room, 'action': action, 'target': target}

    # Resolve actions: move everyone first
    for player in alive:
        act = actions[player['id']]
        old_location = player['location']
        player['location'] = act['room']
        if old_location != act['room']:
            events.append(f"Round {state['round']}: {player['name']} moved from {old_location} to {act['room']}")

    # Resolve tasks for crewmates
    for player in alive:
        if player['role'] != 'crewmate':
            continue
        act = actions[player['id']]
        if act['action'] == 'do_task':
            for task in player['tasks']:
                if not task['done'] and task['room'] == player['location']:
                    task['done'] = True
                    player['tasks_done'] += 1
                    state['total_tasks_done'] += 1
                    events.append(f"Round {state['round']}: {player['name']} completed '{task['name']}' in {player['location']}")
                    break

    # Resolve impostor kill
    impostor = get_impostor(state)
    if impostor['alive'] and not impostor['ejected']:
        imp_act = actions.get(impostor['id'])
        if imp_act and imp_act['action'] == 'kill' and not state['kill_cooldown']:
            target_name = imp_act.get('target')
            if target_name:
                # Find target player in same room
                victim = None
                for p in alive:
                    if p['name'] == target_name and p['id'] != impostor['id'] and p['location'] == impostor['location']:
                        victim = p
                        break

                # If target not in room, try to kill anyone in the room
                if not victim:
                    for p in alive:
                        if p['id'] != impostor['id'] and p['location'] == impostor['location'] and p['role'] == 'crewmate':
                            victim = p
                            break

                if victim:
                    victim['alive'] = False
                    state['bodies'].append({'player_id': victim['id'], 'room': victim['location']})
                    state['kill_cooldown'] = True
                    events.append(f"Round {state['round']}: {victim['name']} was killed in {victim['location']}!")
        elif imp_act and imp_act['action'] == 'fake_task':
            events.append(f"Round {state['round']}: {impostor['name']} completed a task in {impostor['location']}")

    return events


def execute_discovery_phase(state):
    """Check if any alive player discovers a body. Returns True if meeting triggered."""
    alive = alive_players(state)
    for body in state['bodies']:
        for player in alive:
            if player['location'] == body['room']:
                dead_player = get_player(state, body['player_id'])
                state['meeting_triggered'] = True
                state['meeting_reason'] = f"{player['name']} found {dead_player['name']}'s body in {body['room']}!"
                state['event_log'].append(f"Round {state['round']}: EMERGENCY! {state['meeting_reason']}")
                return True

    # No body found - if no bodies exist, skip to next round
    if not state['bodies']:
        # No meeting needed, go straight to next round
        return False

    return False


def execute_discussion_phase(state, round_num):
    """Execute one round of discussion for all alive players."""
    alive = alive_players(state)
    for player in alive:
        prompt = generate_discussion_prompt(player, state, round_num)
        result, reasoning, elapsed = call_ai(player, state, 'discussion', prompt)

        state['timing'][player['id']]['last'] = elapsed
        state['timing'][player['id']]['total'] = round(state['timing'][player['id']]['total'] + elapsed, 2)
        state['reasoning'][player['id']] = reasoning

        statement = result.get('statement', 'I have nothing to say.')
        state['discussion_log'].append({
            'player': player['name'],
            'player_id': player['id'],
            'statement': statement,
            'round': round_num,
        })
        state['event_log'].append(f"Round {state['round']}: {player['name']} says: \"{statement}\"")


def execute_voting_phase(state):
    """Execute voting for all alive players. Returns ejection result."""
    alive = alive_players(state)
    votes = {}  # player_id -> vote_target

    for player in alive:
        prompt = generate_vote_prompt(player, state)
        result, reasoning, elapsed = call_ai(player, state, 'vote', prompt)

        state['timing'][player['id']]['last'] = elapsed
        state['timing'][player['id']]['total'] = round(state['timing'][player['id']]['total'] + elapsed, 2)
        state['reasoning'][player['id']] = reasoning

        vote_target = result.get('vote', 'skip')
        vote_reason = result.get('reason', '')
        votes[player['id']] = vote_target

        state['vote_results'][player['id']] = {
            'voter': player['name'],
            'vote': vote_target,
            'reason': vote_reason,
        }
        state['event_log'].append(f"Round {state['round']}: {player['name']} voted for {vote_target}" + (f" ({vote_reason})" if vote_reason else ""))

    # Tally votes
    tally = {}
    for voter_id, target in votes.items():
        if target == 'skip':
            tally['skip'] = tally.get('skip', 0) + 1
        else:
            # Find player by name
            found = False
            for p in alive:
                if p['name'] == target:
                    tally[p['id']] = tally.get(p['id'], 0) + 1
                    found = True
                    break
            if not found:
                tally['skip'] = tally.get('skip', 0) + 1

    # Determine result
    max_votes = max(tally.values()) if tally else 0
    top_voted = [k for k, v in tally.items() if v == max_votes]

    if len(top_voted) == 1 and top_voted[0] != 'skip' and max_votes > 1:
        # Eject the player
        ejected = get_player(state, top_voted[0])
        ejected['ejected'] = True
        ejected['alive'] = False
        state['ejected_this_round'] = ejected['id']

        was_impostor = ejected['role'] == 'impostor'
        state['event_log'].append(
            f"Round {state['round']}: {ejected['name']} was ejected. "
            f"{'They WERE the impostor!' if was_impostor else 'They were NOT the impostor.'}"
        )
        return {
            'ejected': ejected['name'],
            'was_impostor': was_impostor,
            'tally': {(get_player(state, k)['name'] if k != 'skip' else 'Skip'): v for k, v in tally.items()}
        }
    else:
        state['event_log'].append(f"Round {state['round']}: No one was ejected (tie or skip majority).")
        state['ejected_this_round'] = None
        return {
            'ejected': None,
            'was_impostor': None,
            'tally': {(get_player(state, k)['name'] if k != 'skip' else 'Skip'): v for k, v in tally.items()}
        }


# ─── API Endpoints ───────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/start-game', methods=['POST'])
def start_game():
    global GAME_STATE
    data = request.get_json()

    gpt_model = data.get('gpt_model', 'gpt-5.1')
    claude_model = data.get('claude_model', 'claude-haiku-4.5')

    state = init_game_state(gpt_model=gpt_model, claude_model=claude_model)
    GAME_STATE = state

    return jsonify({
        'success': True,
        'game_state': get_client_state(state)
    })


@app.route('/api/game-state', methods=['GET'])
def get_game_state_route():
    global GAME_STATE
    if not GAME_STATE:
        return jsonify({'error': 'No game in progress'}), 400
    return jsonify(get_client_state(GAME_STATE))


@app.route('/api/next-phase', methods=['POST'])
def next_phase():
    """Advance to the next phase of the game."""
    global GAME_STATE
    state = GAME_STATE
    if not state:
        return jsonify({'error': 'No game in progress'}), 400

    if state['game_over']:
        return jsonify({'error': 'Game is over', 'game_state': get_client_state(state)}), 400

    phase = state['phase']
    result_data = {}

    if phase == 'action':
        # Execute action phase
        events = execute_action_phase(state)
        state['event_log'].extend(events)
        state['phase'] = 'discovery'
        result_data['events'] = events

        # Check win after actions (task completion)
        game_over, winner, reason = check_win_conditions(state)
        if game_over:
            state['game_over'] = True
            state['winner'] = winner
            state['win_reason'] = reason
            result_data['game_over'] = True
            result_data['winner'] = winner

    elif phase == 'discovery':
        # Check for body discovery
        meeting = execute_discovery_phase(state)
        if meeting:
            state['phase'] = 'discussion'
            state['discussion_log'] = []
            state['discussion_round'] = 0
            state['vote_results'] = {}
            result_data['meeting'] = True
            result_data['meeting_reason'] = state['meeting_reason']
        else:
            # No meeting — advance to next round
            state['round'] += 1
            state['phase'] = 'action'
            state['kill_cooldown'] = False
            state['bodies'] = []  # Clear bodies for next round
            state['meeting_triggered'] = False
            result_data['meeting'] = False

        # Check win
        game_over, winner, reason = check_win_conditions(state)
        if game_over:
            state['game_over'] = True
            state['winner'] = winner
            state['win_reason'] = reason

    elif phase == 'discussion':
        # Execute one round of discussion
        execute_discussion_phase(state, state['discussion_round'])
        state['discussion_round'] += 1

        if state['discussion_round'] >= 2:
            state['phase'] = 'voting'
        result_data['discussion_round'] = state['discussion_round']

    elif phase == 'voting':
        # Execute voting
        vote_result = execute_voting_phase(state)
        state['phase'] = 'results'
        result_data['vote_result'] = vote_result

        # Check win
        game_over, winner, reason = check_win_conditions(state)
        if game_over:
            state['game_over'] = True
            state['winner'] = winner
            state['win_reason'] = reason

    elif phase == 'results':
        # Clean up and advance to next round
        state['round'] += 1
        state['phase'] = 'action'
        state['kill_cooldown'] = False
        state['bodies'] = []
        state['meeting_triggered'] = False
        state['discussion_log'] = []
        state['discussion_round'] = 0
        state['vote_results'] = {}
        state['ejected_this_round'] = None

        # Check win
        game_over, winner, reason = check_win_conditions(state)
        if game_over:
            state['game_over'] = True
            state['winner'] = winner
            state['win_reason'] = reason

    GAME_STATE = state

    return jsonify({
        'success': True,
        'phase': state['phase'],
        'result': result_data,
        'game_state': get_client_state(state)
    })


def get_client_state(state):
    """Get state formatted for the client (hides impostor role from raw data)."""
    players_client = []
    for p in state['players']:
        players_client.append({
            'id': p['id'],
            'name': p['name'],
            'team': p['team'],
            'color': p['color'],
            'role': p['role'],  # Reveal roles — the spectator sees everything
            'alive': p['alive'],
            'ejected': p['ejected'],
            'location': p['location'],
            'tasks': p['tasks'],
            'tasks_done': p['tasks_done'],
        })

    return {
        'players': players_client,
        'round': state['round'],
        'phase': state['phase'],
        'total_tasks_done': state['total_tasks_done'],
        'total_tasks_needed': state['total_tasks_needed'],
        'bodies': state['bodies'],
        'discussion_log': state['discussion_log'],
        'discussion_round': state.get('discussion_round', 0),
        'vote_results': {
            pid: state['vote_results'][pid]
            for pid in state['vote_results']
        },
        'event_log': state['event_log'][-20:],
        'game_over': state['game_over'],
        'winner': state['winner'],
        'win_reason': state.get('win_reason'),
        'meeting_triggered': state.get('meeting_triggered', False),
        'meeting_reason': state.get('meeting_reason', ''),
        'ejected_this_round': state.get('ejected_this_round'),

        'reasoning': state.get('reasoning', {}),
        'timing': state.get('timing', {}),

        'gpt_display_name': state.get('gpt_display_name', 'GPT 5.1 Medium'),
        'claude_display_name': state.get('claude_display_name', 'Claude Haiku 4.5 Thinking'),
    }


if __name__ == '__main__':
    app.run(debug=True, port=5002)
