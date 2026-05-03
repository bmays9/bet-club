import { fetchTextFiles } from "./load_data.js";
import { showRacecard } from "./race.js";
import {
    allRacesHaveEntries, canEnterRace, computerAutoSelect, computerSelect,
    enterHorse, displayRaceEntries, fillEmptyRacesWithTiredHorses,
    getBestFinishSymbol, getRestIndicator, TRAINER_STYLES
} from './entry.js';
import {
    shuffleArray, buildHorseData, resetPlayerData
} from './initialise.js';
import {
    raceEntries, playerData, horseData, horsePool, raceData, retiredHorses,
    currentSeason, setRaceEntries, setHorseData, setHorsePool, setPlayerData,
    setRaceData, setCurrentSeason, sortPlayerData, STABLE_COLOURS
} from './gameState.js';

export let meeting_number = 0;
export const raceTime = ["1:15", "1:50", "2:25", "3:00", "3:35", "4:10"];
const TOTALHORSES = 144;
let selectedRaceIndex = 0;
export let lineups = [];

// ── STABLE COLOURS — imported from gameState.js (single source of truth) ──────
// Always use p.colourIndex — never derive from current sort position
function playerColour(player) {
    if (!player) return STABLE_COLOURS[0];
    const idx = (player.colourIndex ?? 0) % STABLE_COLOURS.length;
    return STABLE_COLOURS[idx];
}

// ── MEETING / SEASON ──────────────────────────────────────────────────────────
export function incrementMeetingNumber() {
    if (meeting_number < raceData.meetings.length - 1) {
        meeting_number++;
    } else {
        meeting_number = 0;
        setCurrentSeason(currentSeason + 1);
    }
}
export function resetMeetingNumber() {
    meeting_number = 0;
    setCurrentSeason(currentSeason + 1);
}

// ── RACE DATA BUILD ───────────────────────────────────────────────────────────
async function buildRaceData() {
    const data = await fetchTextFiles();
    shuffleArray(data.horsenames);
    // 144 for active horses + 144 for the replacement pool
    data.horsenames = data.horsenames.slice(0, 288);
    const goingOpts = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    data.goings = Array.from({ length: 20 }, () =>
        goingOpts[Math.floor(Math.random() * goingOpts.length)]);
    setRaceData(data);
}

// ── 6. SEASON SUMMARY MODAL ───────────────────────────────────────────────────
export function showSeasonSummary(players, horses, season, onContinue) {
    const sorted = [...players].sort((a, b) => (b.total || 0) - (a.total || 0));
    const champion = sorted[0];
    const betChampion = [...players].sort((a, b) =>
        ((b.betReturned || 0) - (b.betStaked || 0)) - ((a.betReturned || 0) - (a.betStaked || 0)))[0];
    const topHorse = [...horses].sort((a, b) => (b.money || 0) - (a.money || 0))[0];
    const mostWins = [...horses].sort((a, b) => (b.wins || 0) - (a.wins || 0))[0];

    // Table rows for all players
    const playerRows = sorted.map((p, i) => {
        const betPL = (p.betReturned || 0) - (p.betStaked || 0);
        const plClass = betPL >= 0 ? 'text-success' : 'text-danger';
        const colour = playerColour(p);
        return `<tr>
            <td>${i + 1}</td>
            <td><span class="trainer-pill" style="background:${colour.bg}">${p.name}</span></td>
            <td>${p.wins || 0}</td>
            <td>£${(p.prizeWinnings || 0).toLocaleString()}</td>
            <td class="${plClass}">${betPL >= 0 ? '+' : ''}£${Math.abs(betPL).toLocaleString()}</td>
            <td>-£${(p.entries || 0).toLocaleString()}</td>
            <td class="fw-bold">£${(p.total || 0).toLocaleString()}</td>
        </tr>`;
    }).join('');

    const modalEl = document.getElementById('seasonSummaryModal');
    document.getElementById('ss-season').textContent = season;
    document.getElementById('ss-champion').innerHTML =
        `<span class="trainer-pill" style="background:${playerColour(champion).bg}">${champion?.name || '—'}</span>
         <span class="ms-1">£${(champion?.total || 0).toLocaleString()}</span>`;
    document.getElementById('ss-bet-champ').innerHTML =
        `${betChampion?.name || '—'} (+£${Math.max(0, (betChampion?.betReturned || 0) - (betChampion?.betStaked || 0)).toLocaleString()})`;
    document.getElementById('ss-top-horse').textContent =
        topHorse ? `${topHorse.name} (${topHorse.owner || '?'}) — £${(topHorse.money || 0).toLocaleString()}` : '—';
    document.getElementById('ss-most-wins').textContent =
        mostWins ? `${mostWins.name} — ${mostWins.wins} wins` : '—';
    document.getElementById('ss-player-rows').innerHTML = playerRows;

    document.getElementById('ss-continue').onclick = () => {
        bootstrap.Modal.getInstance(modalEl).hide();
        onContinue();
    };

    new bootstrap.Modal(modalEl).show();
}

// ── DISPLAY GAME STATE ────────────────────────────────────────────────────────
export function displayGameState() {
    document.getElementById('gs-meeting').innerHTML =
        `${raceData.meetings[meeting_number]} (${meeting_number + 1} of ${raceData.meetings.length})`;
    document.getElementById('season-number').innerHTML = `Season ${currentSeason} | `;
    document.getElementById('clear-game-state').style.display = 'block';
    document.getElementById('page-info').style.display = 'block';
    document.getElementById('race-screen').style.display = 'none';
    document.getElementById('race-selections').style.display = 'none';
    document.getElementById('player-selections').style.display = 'none';
    document.getElementById('player-stable').style.display = 'none';

    // ── Clear all residual race-screen content ──
    const raceHeader = document.getElementById('racecard-header');
    const raceBody = document.getElementById('racecard-body');
    const betsBody = document.getElementById('bets-body');
    const betStatus = document.getElementById('betting-status');
    const placeTerms = document.getElementById('place-terms');
    if (raceHeader) raceHeader.innerHTML = '';
    if (raceBody) raceBody.innerHTML = '';
    if (betsBody) betsBody.innerHTML =
        '<tr><td colspan="7" class="text-muted text-center small">No bets placed</td></tr>';
    if (betStatus) betStatus.innerHTML = '';
    if (placeTerms) placeTerms.innerHTML = '';

    if (!raceData?.distances) { console.error("Race data not loaded."); return; }

    // ── Season banner (collapsible) ──
    const bannerEl = document.getElementById('season-banner');
    if (bannerEl) {
        if (raceData._lastChampion && meeting_number === 0 && currentSeason > 1) {
            let detail = '';
            if (raceData._retirementNotices?.length)
                detail += `<div class="alert alert-secondary py-1 mb-1" style="font-size:0.75rem">
                    <strong>🪦 Retired:</strong> ${raceData._retirementNotices.join(' · ')}
                </div>`;
            if (raceData._newHorseNotices?.length)
                detail += `<div class="alert alert-info py-1 mb-1" style="font-size:0.75rem">
                    <strong>⭐ New 4-Year-Olds:</strong> ${raceData._newHorseNotices.join(' · ')}
                </div>`;
            bannerEl.innerHTML = `
                <div class="alert alert-warning fw-bold py-1 mb-1 text-center" style="font-size:0.85rem">
                    🏆 Season ${raceData._lastChampionSeason} Champion: <strong>${raceData._lastChampion}</strong>
                </div>
                ${detail ? `<a class="season-banner-toggle" data-bs-toggle="collapse"
                    href="#season-banner-body">▸ Season Notes</a>
                    <div class="collapse" id="season-banner-body">
                        <div class="mt-1">${detail}</div>
                    </div>` : ''}`;
        } else {
            bannerEl.innerHTML = '';
        }
    }

    // ── Meeting races table ──
    let tableHtml = `<tr>
        <th>Time</th><th>Distance</th><th>Class</th><th>Name</th><th>Prize</th>
    </tr>`;
    for (let i = 0; i < 6; i++) {
        const idx = meeting_number * 6 + i;
        tableHtml += `<tr>
            <td>${raceTime[i]}</td>
            <td>${raceData.distances[idx]}</td>
            <td>${raceData.raceclass[idx]}</td>
            <td>${raceData.racenames[idx]}</td>
            <td>£${Number(raceData.prizemoney[idx]).toLocaleString()}</td>
        </tr>`;
    }
    const racesEl = document.getElementById('gs-meeting-races');
    if (racesEl) racesEl.innerHTML = tableHtml;

    // ── Player standings ──
    sortPlayerData();
    let playerTableHtml = `<tr>
        <th>Pos</th><th>Name</th><th>Wins</th><th>Fees</th><th>Prize £</th><th>Bet P/L</th><th>Total</th>
    </tr>`;
    for (let i = 0; i < playerData.length; i++) {
        const p = playerData[i];
        const betPL = (p.betReturned || 0) - (p.betStaked || 0);
        const plSign = betPL >= 0 ? '+' : '';
        const plCls = betPL >= 0 ? 'text-success' : 'text-danger';
        const colour = playerColour(p);
        const styleLabel = p.trainerStyle && p.trainerStyle !== 'human'
            ? `<span class="small text-muted ms-1" style="font-size:0.65rem;opacity:0.8">${p.trainerStyle.replace(/_/g, ' ')}</span>`
            : '';
        playerTableHtml += `<tr class="${i === 0 ? 'fw-bold' : ''}">
            <td>${i + 1}</td>
            <td style="border-left:4px solid ${colour.bg};padding-left:6px">
                <span class="trainer-pill" style="background:${colour.bg}">${p.name}</span>${styleLabel}
            </td>
            <td>${p.wins || 0}</td>
            <td>-£${(p.entries || 0).toLocaleString()}</td>
            <td>£${(p.prizeWinnings || 0).toLocaleString()}</td>
            <td class="${plCls}">${plSign}£${Math.abs(betPL).toLocaleString()}</td>
            <td class="fw-bold">£${(p.total || 0).toLocaleString()}</td>
        </tr>`;
    }
    const playersEl = document.getElementById('gs-players');
    if (playersEl) playersEl.innerHTML = playerTableHtml;

    // 8. Live sync Hall of Fame
    if (window.HoF) window.HoF.load(horseData, retiredHorses, currentSeason);
}

// ── CLEAR-GAME-STATE BUTTON ───────────────────────────────────────────────────
// entryOrder: the fixed sequence of players for this meeting's entry round.
// Set once per meeting, never re-shuffled mid-round.
let entryOrder = [];

document.getElementById('clear-game-state').addEventListener('click', function () {
    const racesEl = document.getElementById('gs-meeting-races');
    const playersEl = document.getElementById('gs-players');
    const bannerEl = document.getElementById('season-banner');
    if (racesEl) racesEl.innerHTML = "";
    if (playersEl) playersEl.innerHTML = "";
    if (bannerEl) bannerEl.innerHTML = "";
    document.getElementById('next-meeting').innerHTML = "";
    document.getElementById('gs-standings').innerHTML = "";
    document.getElementById('gs-meeting').innerHTML =
        `${raceData.meetings[meeting_number]} | ${raceData.goings[meeting_number]}`;
    document.getElementById('clear-game-state').style.display = "none";
    document.getElementById('page-info').style.display = "none";
    document.getElementById('race-screen').style.display = "none";

    selectedRaceIndex = 0;

    // Shuffle a COPY of playerData for entry order — never shuffle playerData itself
    entryOrder = shuffleArray([...playerData]);

    setRaceEntries({ 0: [], 1: [], 2: [], 3: [], 4: [], 5: [] });
    lineups = [];

    displayRaceSelections();
    displayStable(0);  // index into entryOrder, not playerData
});

// ── RACE SELECTION DISPLAY ────────────────────────────────────────────────────
function displayRaceSelections() {
    let html = `<tr>
        <th>Time</th><th>Dist</th><th>Cls</th><th>Prize</th><th>Name</th>
        <th class="select-horse selection-cell">#1</th>
        <th class="select-horse selection-cell">#2</th>
        <th class="select-horse selection-cell">#3</th>
    </tr>`;
    for (let i = 0; i < 6; i++) {
        const idx = meeting_number * 6 + i;
        const ents = raceEntries[i] || [];
        const sels = [ents[0]?.horseName || "", ents[1]?.horseName || "", ents[2]?.horseName || ""];
        html += `<tr class="race-row ${selectedRaceIndex === i ? 'table-primary' : ''}" data-index="${i}">
            <td>${raceTime[i]}</td>
            <td>${raceData.distances[idx] || "—"}</td>
            <td>${raceData.raceclass[idx]}</td>
            <td>£${raceData.prizemoney[idx]}</td>
            <td>${raceData.racenames[idx]}</td>
            <td class="selection-cell">${sels[0]}</td>
            <td class="selection-cell">${sels[1]}</td>
            <td class="selection-cell">${sels[2]}</td>
        </tr>`;
    }
    document.getElementById('race-selection').innerHTML = html;
    document.querySelectorAll('.race-row').forEach(row => {
        row.addEventListener('click', function () {
            selectedRaceIndex = parseInt(this.getAttribute('data-index'));
            displayRaceSelections();
        });
    });
}

// ── STABLE DISPLAY ────────────────────────────────────────────────────────────
function displayStable(currentPlayerIndex) {
    document.getElementById("race-selections").style.display = "inline-block";
    document.getElementById("player-selections").style.display = "inline-block";
    document.getElementById("player-stable").style.display = "inline-block";
    document.getElementById('page-info').style.display = "inline-block";
    document.getElementById('race-screen').style.display = "none";
    document.getElementById('clear-game-state').style.display = "none";

    // Always read from entryOrder (the fixed shuffled sequence for this meeting)
    const currentPlayer = entryOrder[currentPlayerIndex];
    const playerName = currentPlayer.name;
    const colour = playerColour(currentPlayer);  // reads currentPlayer.colourIndex

    const titleEl = document.getElementById('stable-title');
    if (titleEl) {
        titleEl.textContent = `${playerName}'s Stable`;
        titleEl.style.cssText = `background:${colour.bg};color:#fff;padding:4px 12px;
            border-radius:4px;font-size:0.85rem;font-weight:700;
            letter-spacing:0.5px;margin-bottom:6px;display:inline-block;`;
    }

    document.getElementById('page-info').innerHTML = `
        <button id="confirm-selections" class="btn btn-sm btn-success fw-bold">✓ Finish</button>
        <button id="auto-selections"    class="btn btn-sm btn-outline-secondary ms-1">⚡ Auto</button>`;

    let confirmBtn = document.getElementById("confirm-selections");
    let testBtn = document.getElementById("auto-selections");
    confirmBtn.disabled = true;

    let playerHorses = horseData.filter(h => h.owner === playerName);
    const distanceKeys = ["5f", "1m", "1m2f", "1m4f", "2m", "2m4f", "3m", "4m"];

    if (!currentPlayer.human) {
        if (currentSeason === 1 && meeting_number < 3) {
            computerAutoSelect(playerName, meeting_number);
        } else {
            computerSelect(playerName, meeting_number);
            fillEmptyRacesWithTiredHorses(playerName, meeting_number);
        }
        displayRaceSelections();
        confirmBtn.disabled = false;
        testBtn.disabled = true;
    } else {
        testBtn.disabled = false;
    }

    playerHorses.sort((a, b) => b.rest !== a.rest ? b.rest - a.rest : (b.money || 0) - (a.money || 0));

    let stableHtml = `<tr>
        <th>Sel</th><th>Fit</th><th>Name</th><th>Age</th><th>Form</th>
        <th>Runs</th><th>£</th><th>W</th>
        <th class="dist-sprint">5f</th><th class="dist-sprint">1m</th>
        <th class="dist-mid">1m2f</th><th class="dist-mid">1m4f</th><th class="dist-mid">2m</th>
        <th class="dist-stay">2m4f</th><th class="dist-stay">3m</th><th class="dist-stay">4m</th>
    </tr>`;

    for (let i = 0; i < playerHorses.length; i++) {
        const horse = playerHorses[i];
        const restIndicator = getRestIndicator(horse.rest);
        const fitColour = horse.rest <= -1 ? '#c0392b' : horse.rest === 0 ? '#e67e22'
            : horse.rest === 1 ? '#f1c40f' : horse.rest === 2 ? '#27ae60'
                : horse.rest === 3 ? '#1abc9c' : '#7f8c8d';
        const fitDot = `<span class="fitness-dot" style="background:${fitColour}" title="Rest:${horse.rest}"></span>`;

        const distanceResults = distanceKeys.map(dk => {
            const hist = horse.history.filter(e => e.distance === dk);
            let bestPos = null;
            hist.forEach(e => { if (!bestPos || e.position < bestPos) bestPos = e.position; });
            let label = "";
            if (bestPos === 1) label = "1st";
            else if (bestPos === 2) label = "2nd";
            else if (bestPos === 3) label = "3rd";
            else if ([4, 5, 6].includes(bestPos)) label = bestPos + "th";
            else if (bestPos > 6 || bestPos === 0) label = "0";
            return `<td>${getBestFinishSymbol(label)}</td>`;
        }).join('');

        let enteredRaceIndex = null;
        for (let j = 0; j < 6; j++) {
            if (raceEntries[j].some(e => e.horseName === horse.name)) { enteredRaceIndex = j; break; }
        }
        const entrySymbol = enteredRaceIndex !== null ? `${enteredRaceIndex + 1}` : "➤";
        const rowClass = enteredRaceIndex !== null ? "table-active" : "";

        const formBadges = (horse.form || '').split('').map(ch => {
            if (ch === '/') return `<span class="form-sep">/</span>`;
            const cls = ch === '1' ? 'form-1' : ch === '2' ? 'form-2' : ch === '3' ? 'form-3'
                : ch === '0' ? 'form-0' : ['4', '5', '6'].includes(ch) ? 'form-4' : 'form-7';
            return `<span class="form-badge ${cls}">${ch}</span>`;
        }).join('');

        stableHtml += `<tr class="${rowClass}">
            <td>${entryOrder[currentPlayerIndex].human ? `
                <input type="radio" class="btn-check horse-select" name="btnradio"
                    id="btnradio${i}" autocomplete="off">
                <label class="btn btn-sm btn-outline-primary rounded-pill px-0 py-0 horse-entry-btn"
                    data-horse-name="${horse.name}" for="btnradio${i}">${entrySymbol}</label>
            ` : ''}</td>
            <td class="text-center">${fitDot}${restIndicator}</td>
            <td>${horse.name}</td>
            <td>${horse.age}</td>
            <td><a href="#" class="form-link" data-horse-name="${horse.name}">${formBadges}</a></td>
            <td>${horse.runs || 0}</td>
            <td>£${(horse.money || 0).toLocaleString()}</td>
            <td>${horse.wins || 0}</td>
            ${distanceResults}
        </tr>`;
    }

    document.getElementById('st-horses').innerHTML = stableHtml;

    document.querySelectorAll('.form-link').forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault(); e.stopPropagation();
            showHistoryModal(this.getAttribute('data-horse-name'));
        });
    });

    document.querySelectorAll('.horse-entry-btn').forEach(button => {
        button.addEventListener('click', function () {
            if (selectedRaceIndex === null) { alert("Select a race first."); return; }
            const horseName = this.getAttribute('data-horse-name');
            const pName = entryOrder[currentPlayerIndex].name;
            let alreadyEntered = false;
            for (let i = 0; i < 6; i++) {
                raceEntries[i] = raceEntries[i].filter(e => {
                    if (e.horseName === horseName && e.playerName === pName) { alreadyEntered = true; return false; }
                    return true;
                });
            }
            if (!alreadyEntered) {
                const entered = enterHorse(pName, horseName, selectedRaceIndex);
                if (entered) selectedRaceIndex = (selectedRaceIndex + 1) % 6;
            }
            displayRaceSelections();
            displayStable(currentPlayerIndex);
            confirmBtn.disabled = !allRacesHaveEntries();
        });
    });

    testBtn.onclick = function () {
        const pHorses = horseData.filter(h => h.owner === entryOrder[currentPlayerIndex].name);
        for (let i = 0; i < 6; i++) raceEntries[i] = [];
        for (let i = 0; i < 6; i++) {
            if (pHorses[i]) raceEntries[i].push({
                playerName: entryOrder[currentPlayerIndex].name, horseName: pHorses[i].name
            });
        }
        displayRaceSelections(); displayStable(currentPlayerIndex);
        confirmBtn.disabled = false;
    };

    confirmBtn.onclick = function () {
        if (lineups.length === 0) for (let i = 0; i < 6; i++) lineups.push([]);
        for (let i = 0; i < 6; i++) {
            raceEntries[i].forEach(e => lineups[i].push({
                race: i, horseName: e.horseName, trainer: e.playerName
            }));
        }
        for (let i = 0; i < 6; i++) raceEntries[i] = [];
        currentPlayerIndex++;
        if (currentPlayerIndex >= entryOrder.length) {
            document.getElementById("race-selections").style.display = "none";
            document.getElementById("player-selections").style.display = "none";
            document.getElementById("player-stable").style.display = "none";
            document.getElementById('page-info').style.display = "none";
            showRacecard(0);
        } else {
            displayRaceSelections();
            displayStable(currentPlayerIndex);
            this.disabled = true;
        }
    };

    if (allRacesHaveEntries()) confirmBtn.disabled = false;
}

// ── HISTORY MODAL ─────────────────────────────────────────────────────────────
export function showHistoryModal(horseName) {
    const horse = horseData.find(h => h.name === horseName)
        || retiredHorses.find(h => h.name === horseName);
    const modalBody = document.getElementById('historyModalContent');
    if (!horse) { modalBody.innerHTML = `<p>Horse not found.</p>`; }
    else if (!horse.history?.length) {
        modalBody.innerHTML = `<p>No race history yet for ${horse.name}.</p>`;
    } else {
        const statusBadge = horse.retired
            ? `<span class="badge bg-secondary ms-1">Retired S${horse.retiredSeason}</span>`
            : `<span class="badge bg-success ms-1">Active</span>`;
        document.getElementById('historyModalLabel').innerHTML =
            `${horse.name} <span class="text-muted small">(${horse.owner || '?'})</span>${statusBadge}`;
        const totalEarned = horse.history.reduce((s, r) => s + (r.winnings || 0), 0);
        const rows = horse.history.map(r => `<tr>
            <td>S${r.season || 1} W${r.meeting}</td>
            <td>${r.course}</td><td>${r.going}</td><td>${r.distance}</td>
            <td>${r.position === 0 ? '10+' : r.position}</td>
            <td>${r.winnings > 0 ? '£' + r.winnings.toLocaleString() : '—'}</td>
        </tr>`).join('');
        modalBody.innerHTML = `
            <div class="d-flex gap-3 mb-2 small text-muted flex-wrap">
                <span>Age: <strong>${horse.age}</strong></span>
                <span>Runs: <strong>${horse.runs || horse.history.length}</strong></span>
                <span>Wins: <strong>${horse.wins || 0}</strong></span>
                <span>Career: <strong>£${(horse.money || totalEarned).toLocaleString()}</strong></span>
            </div>
            <table class="table table-striped table-sm">
                <thead><tr>
                    <th>Season/Wk</th><th>Course</th><th>Going</th>
                    <th>Dist</th><th>Pos</th><th>Prize</th>
                </tr></thead>
                <tbody>${rows}</tbody>
            </table>`;
    }
    new bootstrap.Modal(document.getElementById('historyModal')).show();
}

// ── RUN GAME ──────────────────────────────────────────────────────────────────
export async function runHorseRacing(players) {
    await buildRaceData();

    const PROFILES = ['favourite_backer', 'outsider', 'each_way', 'high_risk',
        'form_follower', 'own_horse', 'cautious'];

    const colourIndices = [...Array(STABLE_COLOURS.length).keys()];
    shuffleArray(colourIndices);

    // Shuffle styles so AI players get varied personalities each game
    const stylePool = [...TRAINER_STYLES];
    shuffleArray(stylePool);

    const builtData = resetPlayerData(players).map((p, i) => ({
        ...p,
        colourIndex: colourIndices[i % colourIndices.length],
        bettingProfile: p.human ? null : PROFILES[Math.floor(Math.random() * PROFILES.length)],
        trainerStyle: p.human ? 'human' : stylePool[i % stylePool.length]
    }));

    setPlayerData(builtData);
    setHorseData(buildHorseData(false));
    setHorsePool(buildHorseData(true));
    displayGameState();
}
