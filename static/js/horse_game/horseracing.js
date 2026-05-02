import {
    fetchTextFiles
} from "./load_data.js";
import {
    showRacecard
} from "./race.js";
import {
    addDistanceFormSymbols,
    allEntries,
    allRacesHaveEntries,
    canEnterRace,
    computerAutoSelect,
    computerSelect,
    enterHorse,
    displayRaceEntries,
    fillEmptyRacesWithTiredHorses,
    getBestFinishSymbol,
    getRestIndicator
} from './entry.js';
import {
    shuffleArray,
    buildHorseData,
    resetPlayerData
} from './initialise.js';
import {
    raceEntries,
    playerData,
    horseData,
    horsePool,
    raceData,
    retiredHorses,
    currentSeason,
    setRaceEntries,
    setHorseData,
    setHorsePool,
    setPlayerData,
    setRaceData,
    setCurrentSeason,
    sortPlayerData
} from './gameState.js';

export let meeting_number = 0;
export const raceTime = ["1:15", "1:50", "2:25", "3:00", "3:35", "4:10"];
let players = [];
const TOTALHORSES = 144;
export let going = [];
let selectedRaceIndex = 0;
export let lineups = [];

// ── MEETING / SEASON COUNTER ──────────────────────────────────────────────────

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
    data.horsenames = data.horsenames.slice(0, TOTALHORSES);

    const goingOptions = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    data.goings = Array.from({ length: 20 }, () =>
        goingOptions[Math.floor(Math.random() * goingOptions.length)]
    );

    setRaceData(data);
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

    if (!raceData || !raceData.distances) {
        console.error("Race data not loaded.");
        return;
    }

    // ── 12. Banner: collapsible season notes card ──
    const bannerEl = document.getElementById('season-banner');
    if (bannerEl) {
        if (raceData._lastChampion && meeting_number === 0 && currentSeason > 1) {
            let detailHtml = '';
            if (raceData._retirementNotices?.length) {
                detailHtml += `<div class="alert alert-secondary py-1 mb-1" style="font-size:0.75rem">
                    <strong>🪦 Retired:</strong> ${raceData._retirementNotices.join(' &nbsp;·&nbsp; ')}
                </div>`;
            }
            if (raceData._newHorseNotices?.length) {
                detailHtml += `<div class="alert alert-info py-1 mb-1" style="font-size:0.75rem">
                    <strong>⭐ New 2-Year-Olds:</strong> ${raceData._newHorseNotices.join(' &nbsp;·&nbsp; ')}
                </div>`;
            }
            bannerEl.innerHTML = `
                <div class="alert alert-warning fw-bold py-1 mb-1 text-center" style="font-size:0.85rem">
                    🏆 Season ${raceData._lastChampionSeason} Champion: <strong>${raceData._lastChampion}</strong>
                </div>
                ${detailHtml ? `
                <a class="season-banner-toggle" id="season-banner-toggle"
                   data-bs-toggle="collapse" href="#season-banner-body" role="button">
                   ▸ Season Notes (retirements & new horses)
                </a>
                <div class="collapse" id="season-banner-body">
                    <div class="season-banner-body mt-1">${detailHtml}</div>
                </div>` : ''}`;
        } else {
            bannerEl.innerHTML = '';
        }
    }

    // ── Meeting races table ──
    let tableHtml = `
        <tr>
            <th>Time</th><th>Distance</th><th>Name</th><th>Prize Money</th>
        </tr>`;
    for (let i = 0; i < 6; i++) {
        const idx = meeting_number * 6 + i;
        tableHtml += `
            <tr>
                <td>${raceTime[i]}</td>
                <td>${raceData.distances[idx]}</td>
                <td>${raceData.racenames[idx]}</td>
                <td>£${Number(raceData.prizemoney[idx]).toLocaleString()}</td>
            </tr>`;
    }
    const racesEl = document.getElementById('gs-meeting-races');
    if (racesEl) racesEl.innerHTML = tableHtml;

    sortPlayerData();
    let playerTableHtml = `
        <tr>
            <th>Pos</th><th>Name</th><th>Wins</th><th>Fees</th><th>Prize £</th><th>Bet P/L</th><th>Total</th>
        </tr>`;
    for (let i = 0; i < playerData.length; i++) {
        const p = playerData[i];
        const bold = i === 0 ? 'fw-bold' : '';
        const betPL = (p.winnings || 0) - (p.betting || 0);
        const plSign = betPL >= 0 ? '+' : '';
        const plClass = betPL >= 0 ? 'text-success' : 'text-danger';
        // Stable colour: find original player index (order set at game start)
        const origIdx = playerData.findIndex(pd => pd.name === p.name);
        const colour = STABLE_COLOURS[origIdx % STABLE_COLOURS.length];
        playerTableHtml += `
            <tr class="${bold}">
                <td>${i + 1}</td>
                <td style="border-left:4px solid ${colour.bg};padding-left:6px">
                    <span class="trainer-pill" style="background:${colour.bg}">${p.name}</span>
                </td>
                <td>${p.wins || 0}</td>
                <td>£${(p.entries || 0).toLocaleString()}</td>
                <td>£${(p.winnings || 0).toLocaleString()}</td>
                <td class="${plClass}">${plSign}£${Math.abs(betPL).toLocaleString()}</td>
                <td>£${(p.total || 0).toLocaleString()}</td>
            </tr>`;
    }
    document.getElementById('gs-players').innerHTML = playerTableHtml;

    // Push live data to Hall of Fame if open in the same window
    if (window.HoF) {
        window.HoF.load(horseData, retiredHorses, currentSeason);
    }
}

// ── CLEAR-GAME-STATE BUTTON ───────────────────────────────────────────────────

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
    shuffleArray(playerData);
    setRaceEntries({ 0: [], 1: [], 2: [], 3: [], 4: [], 5: [] });
    lineups = [];

    displayRaceSelections();
    displayStable(0);
});

// ── RACE SELECTIONS DISPLAY ───────────────────────────────────────────────────

function displayRaceSelections() {
    let selectionHtml = `
        <tr>
            <th>Time</th><th>Dist</th><th>Cls</th><th>Prize</th><th>Name</th>
            <th class="select-horse selection-cell">#1</th>
            <th class="select-horse selection-cell">#2</th>
            <th class="select-horse selection-cell">#3</th>
        </tr>`;

    for (let i = 0; i < 6; i++) {
        const idx = meeting_number * 6 + i;
        const distance = raceData.distances[idx] || "—";
        const rname = raceData.racenames[idx];
        const rprize = raceData.prizemoney[idx];
        const rclass = raceData.raceclass[idx];
        const ents = raceEntries[i] || [];
        const sels = [ents[0]?.horseName || "", ents[1]?.horseName || "", ents[2]?.horseName || ""];

        selectionHtml += `
            <tr class="race-row ${selectedRaceIndex === i ? 'table-primary' : ''}" data-index="${i}">
                <td>${raceTime[i]}</td>
                <td>${distance}</td>
                <td>${rclass}</td>
                <td>£${rprize}</td>
                <td>${rname}</td>
                <td class="selection-cell">${sels[0]}</td>
                <td class="selection-cell">${sels[1]}</td>
                <td class="selection-cell">${sels[2]}</td>
            </tr>`;
    }

    document.getElementById('race-selection').innerHTML = selectionHtml;

    document.querySelectorAll('.race-row').forEach(row => {
        row.addEventListener('click', function () {
            selectedRaceIndex = parseInt(this.getAttribute('data-index'));
            displayRaceSelections();
        });
    });
}

// ── STABLE COLOURS — must match race.js exactly ──────────────────────────────
const STABLE_COLOURS = [
    { bg: '#1a6b3c', label: 'green' },
    { bg: '#c0392b', label: 'red' },
    { bg: '#1a3a8f', label: 'blue' },
    { bg: '#d4a017', label: 'yellow' },
    { bg: '#c0680a', label: 'orange' },
    { bg: '#6b2fa0', label: 'purple' },
];

// ── STABLE DISPLAY ────────────────────────────────────────────────────────────

function displayStable(currentPlayerIndex) {
    document.getElementById("race-selections").style.display = "inline-block";
    document.getElementById("player-selections").style.display = "inline-block";
    document.getElementById("player-stable").style.display = "inline-block";
    document.getElementById('page-info').style.display = "inline-block";
    document.getElementById('race-screen').style.display = "none";
    document.getElementById('clear-game-state').style.display = "none";

    const playerName = playerData[currentPlayerIndex].name;
    const colour = STABLE_COLOURS[currentPlayerIndex % STABLE_COLOURS.length];

    // Colour the stable title banner with the player's stable colour
    const titleEl = document.getElementById('stable-title');
    if (titleEl) {
        titleEl.textContent = `${playerName}'s Stable`;
        titleEl.style.cssText = `
            background:${colour.bg};color:#fff;padding:4px 12px;
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

    // ── AI or Human? ──
    if (!playerData[currentPlayerIndex].human) {
        // AI: auto-select, then immediately enable Finish
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
        // Human: enable Test button
        testBtn.disabled = false;
    }

    // Sort stable: rest desc, then money desc
    playerHorses.sort((a, b) => b.rest !== a.rest ? b.rest - a.rest : (b.money || 0) - (a.money || 0));

    let stableHtml = `
        <tr>
            <th>Sel</th><th>Fit</th><th>Name</th><th>Age</th><th>Form</th>
            <th>Runs</th><th>£</th><th>W</th>
            <th class="dist-sprint">5f</th>
            <th class="dist-sprint">1m</th>
            <th class="dist-mid">1m2f</th>
            <th class="dist-mid">1m4f</th>
            <th class="dist-mid">2m</th>
            <th class="dist-stay">2m4f</th>
            <th class="dist-stay">3m</th>
            <th class="dist-stay">4m</th>
        </tr>`;

    for (let i = 0; i < playerHorses.length; i++) {
        const horse = playerHorses[i];
        const restIndicator = getRestIndicator(horse.rest);
        // Fitness dot — same colour logic as racecard
        const fitColour = horse.rest <= -1 ? '#c0392b'
            : horse.rest === 0 ? '#e67e22'
                : horse.rest === 1 ? '#f1c40f'
                    : horse.rest === 2 ? '#27ae60'
                        : horse.rest === 3 ? '#1abc9c'
                            : '#7f8c8d';
        const fitDot = `<span class="fitness-dot" style="background:${fitColour}" title="Rest: ${horse.rest}"></span>`;

        const distanceResults = distanceKeys.map(distKey => {
            const historyAtDist = horse.history.filter(e => e.distance === distKey);
            let bestPos = null;
            historyAtDist.forEach(e => { if (!bestPos || e.position < bestPos) bestPos = e.position; });
            let posLabel = "";
            if (bestPos === 1) posLabel = "1st";
            else if (bestPos === 2) posLabel = "2nd";
            else if (bestPos === 3) posLabel = "3rd";
            else if ([4, 5, 6].includes(bestPos)) posLabel = bestPos + "th";
            else if (bestPos > 6 || bestPos === 0) posLabel = "0";
            return `<td>${getBestFinishSymbol(posLabel)}</td>`;
        }).join('');

        let enteredRaceIndex = null;
        for (let j = 0; j < 6; j++) {
            if (raceEntries[j].some(e => e.horseName === horse.name)) {
                enteredRaceIndex = j; break;
            }
        }
        const entrySymbol = enteredRaceIndex !== null ? `${enteredRaceIndex + 1}` : "➤";
        const rowClass = enteredRaceIndex !== null ? "table-active" : "";

        const formBadges = (() => {
            const f = horse.form || '';
            return f.split('').map(ch => {
                if (ch === '/') return `<span class="form-sep">/</span>`;
                const cls = ch === '1' ? 'form-1' : ch === '2' ? 'form-2' : ch === '3' ? 'form-3' : ch === '0' ? 'form-0' : ['4', '5', '6'].includes(ch) ? 'form-4' : 'form-7';
                return `<span class="form-badge ${cls}">${ch}</span>`;
            }).join('');
        })();

        stableHtml += `
            <tr class="${rowClass}">
                <td>
                    ${playerData[currentPlayerIndex].human ? `
                        <input type="radio" class="btn-check horse-select" name="btnradio" id="btnradio${i}" autocomplete="off">
                        <label class="btn btn-sm btn-outline-primary rounded-pill px-0 py-0 horse-entry-btn"
                            data-horse-name="${horse.name}" for="btnradio${i}">${entrySymbol}</label>
                    ` : ''}
                </td>
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

    // Form link → history modal
    document.querySelectorAll('.form-link').forEach(link => {
        link.addEventListener('click', function (event) {
            event.preventDefault();
            showHistoryModal(this.getAttribute('data-horse-name'));
        });
    });

    // Horse entry button
    document.querySelectorAll('.horse-entry-btn').forEach(button => {
        button.addEventListener('click', function () {
            if (selectedRaceIndex === null) { alert("Please select a race first."); return; }
            const horseName = this.getAttribute('data-horse-name');
            const pName = playerData[currentPlayerIndex].name;
            let alreadyEntered = false;

            for (let i = 0; i < 6; i++) {
                raceEntries[i] = raceEntries[i].filter(entry => {
                    if (entry.horseName === horseName && entry.playerName === pName) {
                        alreadyEntered = true; return false;
                    }
                    return true;
                });
            }

            if (!alreadyEntered) {
                const entered = enterHorse(pName, horseName, selectedRaceIndex);
                if (entered) {
                    selectedRaceIndex = (selectedRaceIndex + 1) % 6;
                }
            }

            displayRaceSelections();
            displayStable(currentPlayerIndex);
            confirmBtn.disabled = !allRacesHaveEntries();
        });
    });

    // Test button: auto-fill first 6 horses
    testBtn.onclick = function () {
        const pHorses = horseData.filter(h => h.owner === playerData[currentPlayerIndex].name);
        for (let i = 0; i < 6; i++) raceEntries[i] = [];
        for (let i = 0; i < 6; i++) {
            if (pHorses[i]) raceEntries[i].push({ playerName: playerData[currentPlayerIndex].name, horseName: pHorses[i].name });
        }
        displayRaceSelections();
        displayStable(currentPlayerIndex);
        confirmBtn.disabled = false;
    };

    // Confirm button: lock in entries and move to next player (or start racing)
    confirmBtn.onclick = function () {
        if (lineups.length === 0) {
            for (let i = 0; i < 6; i++) lineups.push([]);
        }
        for (let i = 0; i < 6; i++) {
            raceEntries[i].forEach(entry => {
                lineups[i].push({ race: i, horseName: entry.horseName, trainer: entry.playerName });
            });
        }
        for (let i = 0; i < 6; i++) raceEntries[i] = [];

        currentPlayerIndex++;

        if (currentPlayerIndex >= playerData.length) {
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
    // Search both active and retired horses
    const horse = horseData.find(h => h.name === horseName)
        || retiredHorses.find(h => h.name === horseName);
    const modalBody = document.getElementById('historyModalContent');

    if (!horse) {
        modalBody.innerHTML = `<p>Horse not found.</p>`;
    } else if (!horse.history || horse.history.length === 0) {
        modalBody.innerHTML = `<p>No race history yet for ${horse.name}.</p>`;
    } else {
        const statusBadge = horse.retired
            ? `<span class="badge bg-secondary ms-1">Retired S${horse.retiredSeason}</span>`
            : `<span class="badge bg-success ms-1">Active</span>`;

        document.getElementById('historyModalLabel').innerHTML =
            `${horse.name} <span class="text-muted small">(${horse.owner || '?'})</span>${statusBadge}`;

        const totalEarned = horse.history.reduce((s, r) => s + (r.winnings || 0), 0);
        const totalWins = horse.history.filter(r => r.position === 1).length;

        const rows = horse.history.map(r => `
            <tr>
                <td>S${r.season || 1} W${r.meeting}</td>
                <td>${r.course}</td>
                <td>${r.going}</td>
                <td>${r.distance}</td>
                <td>${r.position === 0 ? '10+' : r.position}</td>
                <td>${r.winnings > 0 ? '£' + r.winnings.toLocaleString() : '—'}</td>
            </tr>`).join('');

        modalBody.innerHTML = `
            <div class="d-flex gap-3 mb-2 small text-muted flex-wrap">
                <span>Age: <strong>${horse.age}</strong></span>
                <span>Runs: <strong>${horse.runs || horse.history.length}</strong></span>
                <span>Wins: <strong>${horse.wins || totalWins}</strong></span>
                <span>Career: <strong>£${(horse.money || totalEarned).toLocaleString()}</strong></span>
            </div>
            <table class="table table-striped table-sm">
                <thead>
                    <tr><th>Season/Wk</th><th>Course</th><th>Going</th><th>Dist</th><th>Pos</th><th>Prize</th></tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>`;
    }

    new bootstrap.Modal(document.getElementById('historyModal')).show();
}

// ── RUN GAME ──────────────────────────────────────────────────────────────────

export async function runHorseRacing(players) {
    await buildRaceData();

    const PROFILES = ['favourite_backer', 'outsider', 'each_way', 'high_risk', 'form_follower', 'own_horse', 'cautious'];

    const builtData = resetPlayerData(players).map(p => ({
        ...p,
        // Human players have no profile; AI players get one randomly assigned
        bettingProfile: p.human ? null : PROFILES[Math.floor(Math.random() * PROFILES.length)]
    }));

    setPlayerData(builtData);
    setHorseData(buildHorseData(false));
    setHorsePool(buildHorseData(true));
    displayGameState();
}
