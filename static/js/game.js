// ═══ DOM References ════════════════════════════════════════════════
const modalOverlay = document.getElementById('modal-overlay');
const gptModelSelect = document.getElementById('gpt-model');
const claudeModelSelect = document.getElementById('claude-model');
const btnRun = document.getElementById('btn-run');
const gameContainer = document.getElementById('game-container');

const roundNumberEl = document.getElementById('round-number');
const phaseIndicator = document.getElementById('phase-indicator');
const phaseStatus = document.getElementById('phase-status');
const taskBarFill = document.getElementById('task-bar-fill');
const taskCount = document.getElementById('task-count');

const discussionPanel = document.getElementById('discussion-panel');
const discussionLog = document.getElementById('discussion-log');
const votingPanel = document.getElementById('voting-panel');
const voteResults = document.getElementById('vote-results');
const ejectionBanner = document.getElementById('ejection-banner');
const eventLogEl = document.getElementById('event-log');
const bodyIndicators = document.getElementById('body-indicators');
const shipInterior = document.querySelector('.ship-interior');
const mapPlayers = document.getElementById('map-players');
const mapBodies = document.getElementById('map-bodies');

const gameOverOverlay = document.getElementById('game-over-overlay');
const gameOverContent = document.getElementById('game-over-content');
const gameOverIcon = document.getElementById('game-over-icon');
const gameOverTitle = document.getElementById('game-over-title');
const gameOverSubtitle = document.getElementById('game-over-subtitle');

// Ejection cinematic
const ejectCinematic = document.getElementById('eject-cinematic');
const ejectCrew = document.getElementById('eject-crew');
const ejectText = document.getElementById('eject-text');
const ejectRole = document.getElementById('eject-role');

const PLAYER_IDS = ['gpt-1', 'gpt-2', 'gpt-3', 'claude-1', 'claude-2', 'claude-3'];
const ROOMS = ['Cafeteria', 'Electrical', 'MedBay', 'Navigation', 'Reactor'];

// Among Us authentic colors
const CREW_COLORS = {
    'gpt-1':    '#c51111',
    'gpt-2':    '#132ed1',
    'gpt-3':    '#38fedc',
    'claude-1': '#117f2d',
    'claude-2': '#f5f557',
    'claude-3': '#ee7621'
};

let isRunning = false;
let lastState = null;
let wanderTimer = null;
const playerEls = {};
const bodyEls = {};
const playerPos = {};
const playerRoom = {};
const playerMoveUntil = {};
const playerIdleTimers = {};

const PLAYER_W = 34;
const PLAYER_H = 40;
const ROOM_PADDING = 14;

// ═══ INIT ══════════════════════════════════════════════════════════
btnRun.addEventListener('click', startGame);

// ═══ CREWMATE SVG GENERATOR ═══════════════════════════════════════
function crewmateSVG(color, size = 32) {
    return `<svg viewBox="0 0 80 90" width="${size}" height="${size * 90/80}">
        <path d="M12 36 C12 24 18 18 28 18 L28 62 C18 60 12 52 12 42 Z" fill="${color}" opacity="0.85"/>
        <path d="M28 18 C28 6 38 4 50 6 C62 8 68 16 68 30 L68 58 C68 70 60 76 50 78 L50 84 C50 88 46 90 42 90 L36 90 C32 90 28 88 28 84 L28 76 C18 73 14 66 14 58 L14 32 C14 24 18 20 28 18 Z" fill="${color}"/>
        <ellipse cx="52" cy="30" rx="12" ry="9" fill="#1eaed8"/>
        <ellipse cx="56" cy="27" rx="4" ry="3" fill="rgba(255,255,255,0.5)"/>
    </svg>`;
}

// Dead body = half crewmate (bottom half + bone)
function deadBodySVG(color) {
    return `<div class="body-marker">
        <svg viewBox="0 0 60 30" width="32" height="16">
            <ellipse cx="30" cy="15" rx="19" ry="14" fill="${color}"/>
            <rect x="27" y="17" width="11" height="13" rx="4" fill="${color}"/>
            <rect x="11" y="17" width="11" height="13" rx="4" fill="${color}"/>
        </svg>
        <span class="body-bone">&#x1F9B4;</span>
    </div>`;
}

// ═══ START GAME ════════════════════════════════════════════════════
async function startGame() {
    const gptModel = gptModelSelect.value;
    const claudeModel = claudeModelSelect.value;

    btnRun.disabled = true;
    btnRun.querySelector('.btn-text').textContent = 'LAUNCHING...';

    try {
        const res = await fetch('/api/start-game', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gpt_model: gptModel, claude_model: claudeModel })
        });
        const data = await res.json();
        if (data.success) {
            modalOverlay.classList.add('hidden');
            gameContainer.classList.remove('hidden');
            updateUI(data.game_state);
            startWanderLoop();
            runGameLoop();
        }
    } catch (err) {
        console.error('Start error:', err);
        alert('Failed to start. Check console.');
        btnRun.disabled = false;
        btnRun.querySelector('.btn-text').textContent = 'START GAME';
    }
}

// ═══ GAME LOOP ═════════════════════════════════════════════════════
async function runGameLoop() {
    if (isRunning) return;
    isRunning = true;

    while (isRunning) {
        const stateRes = await fetch('/api/game-state');
        if (!stateRes.ok) break;
        const state = await stateRes.json();
        if (state.error) break;

        if (state.game_over) { showGameOver(state); isRunning = false; break; }

        updateUI(state);
        setPhaseDisplay(state.phase);

        await sleep(1000);

        // Advance phase
        try {
            const phaseRes = await fetch('/api/next-phase', { method: 'POST' });
            const pd = await phaseRes.json();

            if (!pd.success) {
                phaseStatus.textContent = 'Error: ' + (pd.error || 'Unknown');
                if (pd.game_state && pd.game_state.game_over) showGameOver(pd.game_state);
                isRunning = false; break;
            }

            updateUI(pd.game_state);
            const r = pd.result || {};

            // Action events
            if (r.events && r.events.length) {
                phaseStatus.textContent = r.events[r.events.length - 1];
                await sleep(1500);
            }

            // Meeting triggered
            if (r.meeting) {
                phaseStatus.textContent = r.meeting_reason || 'Emergency meeting!';
                showMeetingAlert(r.meeting_reason);
                await sleep(2500);
            }

            // Vote result — show cinematic ejection
            if (r.vote_result) {
                showVoteResults(r.vote_result, pd.game_state);
                if (r.vote_result.ejected) {
                    await showEjectionCinematic(r.vote_result, pd.game_state);
                } else {
                    await sleep(2500);
                }
            }

            // Game over
            if (r.game_over || (pd.game_state && pd.game_state.game_over)) {
                showGameOver(pd.game_state); isRunning = false; break;
            }
            if (pd.game_state && pd.game_state.game_over) {
                showGameOver(pd.game_state); isRunning = false; break;
            }

        } catch (err) {
            console.error('Phase error:', err);
            phaseStatus.textContent = 'Connection error';
            isRunning = false; break;
        }

        await sleep(500);
    }
}

// ═══ PHASE DISPLAY ═════════════════════════════════════════════════
function setPhaseDisplay(phase) {
    const labels = {
        action: 'ACTION PHASE',
        discovery: 'DISCOVERY',
        discussion: 'DISCUSSION',
        voting: 'VOTING',
        results: 'RESULTS',
    };
    const statusText = {
        action: 'Players are choosing rooms and actions...',
        discovery: 'Checking for body discoveries...',
        discussion: 'Emergency meeting! Players are discussing...',
        voting: 'Players are casting their votes...',
        results: 'Tallying votes...',
    };

    phaseIndicator.textContent = labels[phase] || phase.toUpperCase();
    phaseIndicator.className = 'phase-badge phase-' + phase;
    phaseStatus.textContent = statusText[phase] || '';

    if (phase === 'action') {
        discussionPanel.classList.add('hidden');
        votingPanel.classList.add('hidden');
        ejectionBanner.classList.add('hidden');
    } else if (phase === 'discussion') {
        discussionPanel.classList.remove('hidden');
        votingPanel.classList.add('hidden');
    }
}

// ═══ UPDATE UI ═════════════════════════════════════════════════════
function updateUI(s) {
    if (!s) return;
    lastState = s;

    roundNumberEl.textContent = s.round;

    // Tasks
    const pct = Math.round((s.total_tasks_done / s.total_tasks_needed) * 100);
    taskBarFill.style.width = pct + '%';
    taskCount.textContent = s.total_tasks_done + '/' + s.total_tasks_needed;

    // Model labels
    el('gpt-model-label').textContent = s.gpt_display_name;
    el('claude-model-label').textContent = s.claude_display_name;

    // Players
    if (s.players) {
        s.players.forEach(p => {
            // Role
            const roleEl = el('role-' + p.id);
            if (roleEl) {
                roleEl.textContent = p.role.toUpperCase();
                roleEl.className = 'pc-role role-' + p.role;
            }

            // Status
            const stEl = el('status-' + p.id);
            if (stEl) {
                if (p.ejected) { stEl.textContent = 'EJECTED'; stEl.className = 'pc-status ejected'; }
                else if (!p.alive) { stEl.textContent = 'DEAD'; stEl.className = 'pc-status dead'; }
                else { stEl.textContent = 'ALIVE'; stEl.className = 'pc-status alive'; }
            }

            // Location
            const locEl = el('location-' + p.id);
            if (locEl) locEl.textContent = p.location;

            // Tasks list
            const tEl = el('tasks-' + p.id);
            if (tEl && p.tasks && p.tasks.length) {
                tEl.innerHTML = p.tasks.map(t =>
                    `<div class="task-item ${t.done ? 'task-done' : ''}">
                        <span class="task-check">${t.done ? '\u2713' : '\u25CB'}</span>
                        <span>${t.name} (${t.room})</span>
                    </div>`
                ).join('');
            } else if (tEl && p.role === 'impostor') {
                tEl.innerHTML = '<div class="task-item task-impostor">Impostor — no tasks</div>';
            }

            // Dead dimming
            const card = el('player-' + p.id);
            if (card) {
                card.classList.toggle('player-dead', !p.alive || p.ejected);
            }
        });

        updateMap(s.players, s.bodies);
    }

    // Timing
    if (s.timing) {
        PLAYER_IDS.forEach(pid => {
            const t = s.timing[pid];
            if (t) {
                const lE = el('time-last-' + pid);
                const tE = el('time-total-' + pid);
                if (lE) lE.textContent = t.last + 's';
                if (tE) tE.textContent = t.total + 's';
            }
        });
    }

    // Reasoning
    if (s.reasoning) {
        PLAYER_IDS.forEach(pid => {
            const rE = el('reasoning-' + pid);
            if (rE && s.reasoning[pid]) rE.textContent = s.reasoning[pid].substring(0, 500);
        });
    }

    // Discussion
    if (s.discussion_log && s.discussion_log.length) {
        discussionPanel.classList.remove('hidden');
        discussionLog.innerHTML = s.discussion_log.map(e => {
            const c = CREW_COLORS[e.player_id] || '#fff';
            return `<div class="chat-bubble" style="border-left-color:${c}">
                <span class="chat-name" style="color:${c}">${e.player}:</span>
                <span class="chat-text">${esc(e.statement)}</span>
            </div>`;
        }).join('');
        discussionLog.scrollTop = discussionLog.scrollHeight;
    }

    // Votes
    if (s.vote_results && Object.keys(s.vote_results).length) {
        votingPanel.classList.remove('hidden');
        voteResults.innerHTML = Object.values(s.vote_results).map(v =>
            `<div class="vote-entry">
                <span class="vote-voter">${v.voter}</span>
                <span class="vote-arrow">\u27A1</span>
                <span class="vote-target">${v.vote}</span>
                ${v.reason ? `<span class="vote-reason">(${esc(v.reason)})</span>` : ''}
            </div>`
        ).join('');
    }

    // Event log
    if (s.event_log) {
        eventLogEl.innerHTML = [...s.event_log].reverse().map(e =>
            `<div class="event-entry">${esc(e)}</div>`
        ).join('');
    }
}

// ═══ MAP UPDATE ════════════════════════════════════════════════════
function updateMap(players, bodies, immediate = false) {
    if (!shipInterior || !mapPlayers || !mapBodies) return;

    // Players
    players.forEach(p => {
        const existing = playerEls[p.id];
        if (p.ejected || !p.alive) {
            if (existing) existing.style.display = 'none';
            return;
        }

        const elp = ensurePlayerEl(p.id, CREW_COLORS[p.id] || '#fff');
        elp.style.display = 'block';
        const roomChanged = playerRoom[p.id] && playerRoom[p.id] !== p.location;
        if (roomChanged || !playerPos[p.id]) {
            movePlayerTo(p.id, p.location, immediate || !playerPos[p.id]);
        }
    });

    // Remove any players not in state
    Object.keys(playerEls).forEach(pid => {
        if (!players.find(p => p.id === pid && p.alive && !p.ejected)) {
            playerEls[pid].style.display = 'none';
        }
    });

    // Bodies
    const bodyIds = new Set((bodies || []).map(b => b.player_id));
    (bodies || []).forEach(b => {
        let be = bodyEls[b.player_id];
        if (!be) {
            const deadP = players.find(p => p.id === b.player_id);
            const color = deadP ? (CREW_COLORS[deadP.id] || '#888') : '#888';
            be = document.createElement('div');
            be.className = 'map-body';
            be.innerHTML = deadBodySVG(color);
            mapBodies.appendChild(be);
            bodyEls[b.player_id] = be;
        }
        const pos = randomPointInRoom(b.room, 18);
        if (pos) {
            be.style.left = `${pos.x}px`;
            be.style.top = `${pos.y}px`;
        }
    });
    Object.keys(bodyEls).forEach(pid => {
        if (!bodyIds.has(pid)) {
            bodyEls[pid].remove();
            delete bodyEls[pid];
        }
    });
}

function ensurePlayerEl(id, color) {
    if (playerEls[id]) return playerEls[id];
    const elp = document.createElement('div');
    elp.className = 'map-player idle';
    elp.id = `map-player-${id}`;
    elp.innerHTML = crewmateSVG(color, PLAYER_W);
    mapPlayers.appendChild(elp);
    playerEls[id] = elp;
    return elp;
}

function getRoomEl(roomName) {
    return document.getElementById('room-' + roomName);
}

function getRoomBounds(roomName) {
    const room = getRoomEl(roomName);
    if (!room) return null;
    return {
        left: room.offsetLeft,
        top: room.offsetTop,
        width: room.offsetWidth,
        height: room.offsetHeight
    };
}

function randomPointInRoom(roomName, padding = ROOM_PADDING) {
    const b = getRoomBounds(roomName);
    if (!b) return null;
    const maxX = Math.max(b.width - PLAYER_W - padding * 2, 0);
    const maxY = Math.max(b.height - PLAYER_H - padding * 2, 0);
    const x = b.left + padding + (maxX ? Math.random() * maxX : 0);
    const y = b.top + padding + (maxY ? Math.random() * maxY : 0);
    return { x, y };
}

function movePlayerTo(id, roomName, immediate = false) {
    const elp = playerEls[id];
    if (!elp) return;
    const dest = randomPointInRoom(roomName, 16);
    if (!dest) return;

    const prev = playerPos[id] || dest;
    const dist = Math.hypot(dest.x - prev.x, dest.y - prev.y);
    const duration = immediate ? 0 : clamp(dist / 120, 0.6, 1.8);

    elp.style.setProperty('--walk-time', `${duration}s`);
    elp.style.left = `${dest.x}px`;
    elp.style.top = `${dest.y}px`;
    playerPos[id] = dest;
    playerRoom[id] = roomName;
    playerMoveUntil[id] = Date.now() + duration * 1000;

    elp.classList.remove('idle');
    elp.classList.add('is-walking');
    if (playerIdleTimers[id]) clearTimeout(playerIdleTimers[id]);
    playerIdleTimers[id] = setTimeout(() => {
        elp.classList.remove('is-walking');
        elp.classList.add('idle');
    }, duration * 1000 + 50);
}

function startWanderLoop() {
    if (wanderTimer) return;
    wanderTimer = setInterval(() => {
        if (!isRunning || !lastState || !lastState.players) return;
        const now = Date.now();
        lastState.players.forEach(p => {
            if (p.ejected || !p.alive) return;
            if (!playerRoom[p.id]) return;
            const lock = playerMoveUntil[p.id] || 0;
            if (now < lock) return;
            movePlayerTo(p.id, playerRoom[p.id], false);
        });
    }, 1200);
}

function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
}

window.addEventListener('resize', () => {
    if (lastState && lastState.players) {
        updateMap(lastState.players, lastState.bodies || [], true);
    }
});

// ═══ MEETING ALERT ═════════════════════════════════════════════════
function showMeetingAlert(reason) {
    ejectionBanner.classList.remove('hidden');
    ejectionBanner.className = 'ejection-banner meeting-alert';
    ejectionBanner.innerHTML = `<span>\uD83D\uDEA8</span> EMERGENCY MEETING<br><small>${esc(reason || '')}</small>`;
}

// ═══ VOTE RESULTS ══════════════════════════════════════════════════
function showVoteResults(vr, state) {
    votingPanel.classList.remove('hidden');

    if (vr.tally) {
        let html = '<div class="vote-tally"><h4>Vote Tally</h4>';
        for (const [name, count] of Object.entries(vr.tally)) {
            html += `<div class="tally-row">
                <span class="tally-name">${name}</span>
                <span class="tally-bar"><span class="tally-fill" style="width:${count * 25}%"></span></span>
                <span class="tally-count">${count}</span>
            </div>`;
        }
        html += '</div>';
        voteResults.innerHTML += html;
    }

    // Inline ejection banner
    if (vr.ejected) {
        ejectionBanner.classList.remove('hidden');
        ejectionBanner.className = 'ejection-banner ejection-result';
        const icon = vr.was_impostor ? '\u2705' : '\u274C';
        const msg = vr.was_impostor
            ? `${vr.ejected} was The Impostor.`
            : `${vr.ejected} was not The Impostor.`;
        ejectionBanner.innerHTML = `<span>${icon}</span> ${vr.ejected} was ejected.<br><small>${msg}</small>`;
    } else {
        ejectionBanner.classList.remove('hidden');
        ejectionBanner.className = 'ejection-banner no-eject';
        ejectionBanner.innerHTML = 'No one was ejected. (Tie or skip majority)';
    }
}

// ═══ EJECTION CINEMATIC ════════════════════════════════════════════
async function showEjectionCinematic(vr, state) {
    // Find color of ejected player
    let color = '#888';
    if (state && state.players) {
        const ep = state.players.find(p => p.name === vr.ejected);
        if (ep) color = CREW_COLORS[ep.id] || '#888';
    }

    // Set crewmate color
    ejectCrew.style.color = color;
    ejectCrew.classList.remove('animate-eject');

    // Set text
    ejectText.textContent = `${vr.ejected} was ejected.`;
    ejectText.style.color = '#e8ecf4';

    const roleMsg = vr.was_impostor
        ? `${vr.ejected} was The Impostor.`
        : `${vr.ejected} was not The Impostor.`;
    ejectRole.textContent = roleMsg;
    ejectRole.style.color = vr.was_impostor ? '#50ef39' : '#ff1c1c';

    // Reset animations
    ejectText.style.animation = 'none';
    ejectRole.style.animation = 'none';
    void ejectText.offsetHeight; // force reflow
    ejectText.style.animation = '';
    ejectRole.style.animation = '';

    // Show cinematic
    ejectCinematic.classList.remove('hidden');

    // Trigger float-away after a beat
    await sleep(800);
    ejectCrew.classList.add('animate-eject');

    // Hold for full animation
    await sleep(4000);

    // Hide
    ejectCinematic.classList.add('hidden');
    ejectCrew.classList.remove('animate-eject');
}

// ═══ GAME OVER ═════════════════════════════════════════════════════
function showGameOver(state) {
    gameOverOverlay.classList.remove('hidden');
    gameOverContent.classList.remove('crew-win', 'imp-win');

    const reasonText = {
        impostor_ejected: 'Impostor was ejected by vote.',
        impostor_dead: 'Impostor was eliminated.',
        tasks_completed: 'All tasks were completed.',
        impostor_kills: 'Impostor outnumbered the crew.',
        max_rounds: 'Max rounds reached — crew wins by safety rule.'
    };

    if (state.winner === 'crewmates') {
        gameOverIcon.textContent = '\uD83D\uDE80';
        gameOverTitle.textContent = 'CREWMATES WIN';
        gameOverSubtitle.textContent = reasonText[state.win_reason] || 'The impostor has been stopped.';
        gameOverContent.classList.add('crew-win');
    } else {
        gameOverIcon.textContent = '\uD83D\uDD2A';
        gameOverTitle.textContent = 'IMPOSTOR WINS';
        gameOverSubtitle.textContent = reasonText[state.win_reason] || 'The impostor has taken over the ship.';
        gameOverContent.classList.add('imp-win');
    }
}

// ═══ HELPERS ═══════════════════════════════════════════════════════
function el(id) { return document.getElementById(id); }

function esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}
